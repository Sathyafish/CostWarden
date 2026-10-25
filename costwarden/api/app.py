import hmac
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from costwarden.accounts import load_accounts
from costwarden.agents.qa import answer
from costwarden.client import get_client
from costwarden.config import Settings, load_settings
from costwarden.llm import get_llm
from costwarden.store import get_store
from costwarden.store.demo import seed_history
from costwarden.view_models import account_rows, savings_trend


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class StartBody(BaseModel):
    account_ids: list[str] | None = None


class ResumeBody(BaseModel):
    value: dict


def create_app(settings: Settings | None = None, *, store=None, client=None, llm=None) -> FastAPI:
    s = settings or load_settings()
    store = store or get_store(s)
    client = client or get_client(s, store)
    llm = llm or get_llm(s)
    accounts = load_accounts(s.accounts_file)
    known_ids = {a.id for a in accounts}

    app = FastAPI(title="CostWarden API")
    app.add_middleware(
        CORSMiddleware, allow_origins=list(s.cors_origins), allow_methods=["GET", "POST"],
        allow_headers=["content-type", "x-api-key"],
    )

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        if s.api_key and not hmac.compare_digest(x_api_key or "", s.api_key):
            raise HTTPException(status_code=401, detail="Missing or invalid API key")

    def check_account(account_id: str | None) -> None:
        if account_id and account_id not in known_ids:
            raise HTTPException(status_code=404, detail=f"Unknown account {account_id}")

    # ---- open routes ---------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/info")
    def info():
        return {"runtime": s.agent_runtime, "store": s.store_backend, "llm": s.llm_provider,
                "demo_seed": s.allow_demo_seed, "auth_required": bool(s.api_key)}

    # ---- protected routes ----------------------------------------------------
    guard = [Depends(require_key)]

    @app.get("/api/accounts", dependencies=guard)
    def list_accounts():
        return [{"id": a.id, "name": a.name, "region": a.region} for a in accounts]

    @app.get("/api/dashboard", dependencies=guard)
    def dashboard(account_id: str | None = Query(default=None)):
        check_account(account_id)
        m = store.metrics(account_id)
        return {
            "account_id": account_id,
            "kpis": {
                "cost_avoided_monthly": m.cost_avoided_monthly,
                "cost_avoided_annualized": round(m.cost_avoided_monthly * 12, 2),
                "cost_avoided_cumulative": m.cost_avoided_cumulative,
                "cleanups": m.cleanups,
                "open_prs": m.open_prs,
            },
            "counts_by_status": m.counts_by_status,
            "by_resource_type": sorted(
                ({"resource_type": k, **v} for k, v in m.by_resource_type.items()),
                key=lambda r: r["savings"], reverse=True),
            "trend": [{"date": d, "value": v} for d, v in savings_trend(store, account_id)],
            "accounts": account_rows(store, accounts),
        }

    @app.get("/api/cleanups", dependencies=guard)
    def cleanups(account_id: str | None = Query(default=None), limit: int = Query(default=20, ge=1, le=200)):
        check_account(account_id)
        return [asdict(r) for r in store.list_cleanups(account_id)[:limit]]

    @app.post("/api/ask", dependencies=guard)
    def ask(body: AskBody):
        a = answer(body.question, store, llm)
        return {"text": a.text, "tool": a.tool, "data": a.data}

    @app.post("/api/runs", dependencies=guard)
    def start_run(body: StartBody):
        for aid in body.account_ids or []:
            check_account(aid)
        try:
            return client.start(body.account_ids)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Run failed to start: {e}") from e

    @app.get("/api/runs/{run_id}", dependencies=guard)
    def run_status(run_id: str):
        try:
            st = client.status(run_id)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(e)) from e
        if not st.get("known", True):
            raise HTTPException(status_code=404, detail="Unknown run")
        return st

    @app.post("/api/runs/{run_id}/resume", dependencies=guard)
    def resume_run(run_id: str, body: ResumeBody):
        try:
            before = client.status(run_id)
            if not before.get("known", True):
                raise HTTPException(status_code=404, detail="Unknown run")
            if not before.get("pending"):
                raise HTTPException(status_code=409, detail="Run is not waiting for input")
            return client.resume(run_id, body.value)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Could not continue the run: {e}") from e

    @app.post("/api/demo/seed", dependencies=guard)
    def demo_seed():
        if not s.allow_demo_seed:
            raise HTTPException(status_code=403, detail="Demo seeding is disabled")
        return {"seeded": seed_history(store)}

    return app
