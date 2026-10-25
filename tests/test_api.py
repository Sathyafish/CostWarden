import pytest
from fastapi.testclient import TestClient

from costwarden.api.app import create_app
from costwarden.client import LocalClient
from costwarden.config import load_settings
from costwarden.llm import FakeLLM
from costwarden.runs import RunService
from costwarden.store.demo import seed_history
from costwarden.store.memory import MemoryStore
from costwarden.agents.entry import Deps
from costwarden.agents.runtime import LocalInvoker
from costwarden.checkpoint import LocalCheckpointer
from costwarden.tools.github_client import FakeGitHubClient


def make(extra_env=None, seed=True):
    env = {"STORE_BACKEND": "memory", "LLM_PROVIDER": "fake", **(extra_env or {})}
    s = load_settings(env=env)
    store = MemoryStore()
    if seed:
        seed_history(store)
    svc = RunService(s, invoker=LocalInvoker(Deps(s, FakeGitHubClient())), store=store, llm=FakeLLM(),
                     checkpointer=LocalCheckpointer(), sleep=lambda _: None)
    return TestClient(create_app(s, store=store, client=LocalClient(svc), llm=FakeLLM())), store


def test_health_and_info_are_open_even_with_key():
    c, _ = make({"API_KEY": "secret"})
    assert c.get("/api/health").json() == {"ok": True}
    assert c.get("/api/info").json()["auth_required"] is True


def test_protected_routes_reject_missing_or_wrong_key():
    c, _ = make({"API_KEY": "secret"})
    assert c.get("/api/dashboard").status_code == 401
    assert c.get("/api/dashboard", headers={"x-api-key": "nope"}).status_code == 401
    assert c.get("/api/dashboard", headers={"x-api-key": "secret"}).status_code == 200


def test_no_key_configured_means_open():
    c, _ = make()
    assert c.get("/api/accounts").status_code == 200


def test_accounts_hide_internals():
    c, _ = make()
    a = c.get("/api/accounts").json()[0]
    assert set(a) == {"id", "name", "region"}


def test_dashboard_kpis_and_shape():
    c, _ = make()
    d = c.get("/api/dashboard").json()
    k = d["kpis"]
    assert k["cost_avoided_monthly"] == round(188.0 + 350.4 + 210.24 + 91.1, 2)
    assert k["cost_avoided_annualized"] == round(k["cost_avoided_monthly"] * 12, 2)
    assert k["cleanups"] == 5 and d["counts_by_status"]["rejected"] == 1
    types = [r["resource_type"] for r in d["by_resource_type"]]
    assert types[0] == "RdsDbInstance" and "EC2Instance" in types  # merged only, ranked by savings
    assert d["by_resource_type"][1]["savings"] == round(210.24 + 91.1, 2)  # the rejected EC2 cleanup is excluded
    assert len(d["trend"]) == 4 and d["trend"][-1]["value"] == k["cost_avoided_monthly"]
    assert {r["account_id"] for r in d["accounts"]} == {"111111111111", "222222222222"}


def test_dashboard_account_filter_and_unknown_account():
    c, _ = make()
    d = c.get("/api/dashboard", params={"account_id": "222222222222"}).json()
    assert d["kpis"]["cost_avoided_monthly"] == round(350.4 + 91.1, 2)
    assert c.get("/api/dashboard", params={"account_id": "999"}).status_code == 404


def test_empty_store_dashboard_is_zeros():
    c, _ = make(seed=False)
    k = c.get("/api/dashboard").json()["kpis"]
    assert k["cost_avoided_monthly"] == 0 and k["cleanups"] == 0


def test_cleanups_newest_first_and_limit():
    c, _ = make()
    rows = c.get("/api/cleanups", params={"limit": 2}).json()
    assert len(rows) == 2 and rows[0]["timestamp"] >= rows[1]["timestamp"]
    assert c.get("/api/cleanups", params={"limit": 0}).status_code == 422


def test_ask_returns_grounded_answer():
    c, store = make()
    r = c.post("/api/ask", json={"question": "what was the last cleanup?"}).json()
    last = store.list_cleanups()[0]
    assert r["tool"] == "last_cleanup" and f"{last.monthly_savings_usd:,.2f}" in r["text"]


def test_ask_validates_input():
    c, _ = make()
    assert c.post("/api/ask", json={"question": ""}).status_code == 422
    assert c.post("/api/ask", json={}).status_code == 422


def test_run_flow_end_to_end():
    c, store = make(seed=False)
    run = c.post("/api/runs", json={"account_ids": ["111111111111"]}).json()
    assert run["pending"]["type"] == "approve_diff"
    rid = run["run_id"]
    assert c.get(f"/api/runs/{rid}").json()["pending"]["account_id"] == "111111111111"
    r = c.post(f"/api/runs/{rid}/resume", json={"value": {"approved": True, "exclude": []}}).json()
    assert r["pending"]["type"] == "confirm_merge"
    r = c.post(f"/api/runs/{rid}/resume", json={"value": {"merged": True}}).json()
    assert r["done"] and r["outcomes"]["111111111111"] == "merged"
    assert c.get("/api/dashboard").json()["kpis"]["cost_avoided_monthly"] > 0


def test_unknown_run_is_404_and_resume_without_pending_is_409():
    c, _ = make(seed=False)
    assert c.get("/api/runs/nope").status_code == 404
    assert c.post("/api/runs/nope/resume", json={"value": {}}).status_code == 404
    run = c.post("/api/runs", json={"account_ids": ["111111111111"]}).json()
    c.post(f"/api/runs/{run['run_id']}/resume", json={"value": {"approved": False}})
    assert c.post(f"/api/runs/{run['run_id']}/resume", json={"value": {"approved": True}}).status_code == 409


def test_start_run_rejects_unknown_account():
    c, _ = make(seed=False)
    assert c.post("/api/runs", json={"account_ids": ["999"]}).status_code == 404


def test_demo_seed_disabled_by_default_and_enabled_by_flag():
    c, _ = make(seed=False)
    assert c.post("/api/demo/seed").status_code == 403
    c2, store = make({"ALLOW_DEMO_SEED": "true"}, seed=False)
    assert c2.post("/api/demo/seed").json() == {"seeded": 5} and len(store.list_cleanups()) == 5


def test_cors_allows_dev_origin_only():
    c, _ = make()
    ok = c.options("/api/dashboard", headers={"Origin": "http://localhost:5173",
                                              "Access-Control-Request-Method": "GET",
                                              "Access-Control-Request-Headers": "x-api-key"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = c.options("/api/dashboard", headers={"Origin": "http://evil.example",
                                               "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_backend_failure_becomes_502_not_500():
    c, _ = make(seed=False)

    class Boom:
        def start(self, *_):
            raise RuntimeError("supervisor down")

        def status(self, *_):
            raise RuntimeError("supervisor down")

    s = load_settings(env={"STORE_BACKEND": "memory", "LLM_PROVIDER": "fake"})
    c = TestClient(create_app(s, store=MemoryStore(), client=Boom(), llm=FakeLLM()))
    r = c.post("/api/runs", json={})
    assert r.status_code == 502 and "supervisor down" in r.json()["detail"]
    assert c.get("/api/runs/x").status_code == 502


def test_lambda_function_url_handler_serves_the_api(monkeypatch):
    import importlib
    import json

    monkeypatch.setenv("STORE_BACKEND", "memory")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("API_KEY", "a-long-shared-secret")
    import costwarden.api.lambda_api as lambda_api

    lambda_api = importlib.reload(lambda_api)

    def event(path, headers=None, method="GET"):
        return {
            "version": "2.0", "rawPath": path, "rawQueryString": "", "headers": {"host": "x.lambda-url.aws", **(headers or {})},
            "requestContext": {"http": {"method": method, "path": path, "sourceIp": "1.2.3.4", "protocol": "HTTP/1.1"}, "stage": "$default"},
            "isBase64Encoded": False,
        }

    ok = lambda_api.handler(event("/api/health"), None)
    assert ok["statusCode"] == 200 and json.loads(ok["body"]) == {"ok": True}
    assert lambda_api.handler(event("/api/accounts"), None)["statusCode"] == 401
    authed = lambda_api.handler(event("/api/accounts", {"x-api-key": "a-long-shared-secret"}), None)
    assert authed["statusCode"] == 200 and len(json.loads(authed["body"])) == 2
