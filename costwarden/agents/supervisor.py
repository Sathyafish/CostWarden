import time
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from costwarden.accounts import Account, load_accounts
from costwarden.agents.narrative import rank_findings, write_risk_summary
from costwarden.agents.runtime import call_with_retry, get_invoker
from costwarden.checkpoint import get_checkpointer
from costwarden.config import Settings, load_settings
from costwarden.llm import get_llm
from costwarden.models import Finding
from costwarden.store import CleanupRecord, get_store, now_iso


def merge(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class RunState(TypedDict, total=False):
    run_id: str
    account_ids: list[str] | None
    findings: Annotated[dict, merge]
    errors: Annotated[dict, merge]
    outcomes: Annotated[dict, merge]
    pr_urls: Annotated[dict, merge]
    plans: Annotated[dict, merge]
    queue: list[str]
    current: str | None
    result: dict | None
    summary: str
    failed_step: str | None


def build_graph(settings: Settings | None = None, *, registry=None, invoker=None, store=None, llm=None,
                summary_llm=None, checkpointer=None, sleep=time.sleep):
    s = settings or load_settings()
    list_accounts = registry or (lambda: load_accounts(s.accounts_file))
    invoker = invoker or get_invoker(s)
    store = store or get_store(s)
    llm = llm or get_llm(s)
    summary_llm = summary_llm or llm
    checkpointer = checkpointer or get_checkpointer(s)

    def accounts_by_id() -> dict[str, Account]:
        return {a.id: a for a in list_accounts()}

    def call(agent: str, payload: dict) -> dict:
        return call_with_retry(invoker, agent, payload, sleep=sleep)

    def fail(state: RunState, step: str, err: Exception) -> dict:
        acct = state["current"]
        return {"errors": {acct: f"{step}: {err}"}, "failed_step": step}

    # ---- nodes -------------------------------------------------------------------
    def load(state: RunState) -> dict:
        known = list(accounts_by_id())
        wanted = state.get("account_ids") or known
        return {"account_ids": [a for a in wanted if a in known], "findings": {}, "errors": {}, "outcomes": {},
                "pr_urls": {}, "plans": {}}

    def discover_all(state: RunState) -> dict:
        accts = accounts_by_id()

        def one(aid: str):
            try:
                data = call("discover", {"account": accts[aid].to_dict()})
                return aid, data["findings"], None
            except Exception as e:  # noqa: BLE001 - one account failing must not stop the rest
                return aid, [], f"discover: {e}"

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(state["account_ids"])))) as pool:
            rows = list(pool.map(one, state["account_ids"]))
        return {
            "findings": {aid: fs for aid, fs, err in rows if not err},
            "errors": {aid: err for aid, _, err in rows if err},
        }

    def plan_queue(state: RunState) -> dict:
        queue, outcomes = [], {}
        for aid in state["account_ids"]:
            if aid in state.get("errors", {}):
                outcomes[aid] = "discovery_failed"
            elif not state["findings"].get(aid):
                outcomes[aid] = "no_findings"
            else:
                queue.append(aid)
        return {"queue": queue, "outcomes": outcomes}

    def next_account(state: RunState) -> dict:
        q = list(state.get("queue", []))
        return {"current": q.pop(0) if q else None, "queue": q, "result": None, "summary": "",
                "failed_step": None}

    def build_result(acct: Account, findings: list[dict]) -> tuple[dict, str]:
        ranked = rank_findings(llm, [Finding.from_dict(f) for f in findings])
        result = call("refactor", {"account": acct.to_dict(), "findings": [f.to_dict() for f in ranked]})
        summary = ""
        if result["edited"]:
            try:
                summary = write_risk_summary(summary_llm, acct.name, result)
            except Exception as e:  # noqa: BLE001 - summary is optional
                summary = f"(risk summary unavailable: {e})"
        return result, summary

    def refactor_node(state: RunState) -> dict:
        acct = accounts_by_id()[state["current"]]
        try:
            result, summary = build_result(acct, state["findings"][acct.id])
        except Exception as e:  # noqa: BLE001
            return fail(state, "refactor", e)
        return {"result": result, "summary": summary, "failed_step": None}

    def approve_diff(state: RunState) -> dict:
        acct = accounts_by_id()[state["current"]]
        result = state["result"]
        if not result["edited"]:
            return {"outcomes": {acct.id: "nothing_to_change"}}
        decision = interrupt({
            "type": "approve_diff", "account_id": acct.id, "account_name": acct.name,
            "diff": result["diff"], "savings_usd": result["savings_usd"], "edited": result["edited"],
            "unmapped": result["unmapped"], "summary": state.get("summary", ""),
            "validation": result["validation_note"],
        })
        if not decision.get("approved"):
            store.record_cleanup(CleanupRecord(acct.id, state["run_id"], now_iso(), result["edited"],
                                               result["savings_usd"], None, "rejected", state.get("summary", "")))
            return {"outcomes": {acct.id: "rejected"}}
        exclude = set(decision.get("exclude") or [])
        if exclude:
            keep = [f for f in state["findings"][acct.id] if f["resource_id"] not in exclude]
            try:
                result, summary = build_result(acct, keep)
            except Exception as e:  # noqa: BLE001
                return fail(state, "refactor", e)
            return {"result": result, "summary": summary, "outcomes": {acct.id: "approved"}}
        return {"outcomes": {acct.id: "approved"}}

    def open_pr_node(state: RunState) -> dict:
        acct = accounts_by_id()[state["current"]]
        result = state["result"]
        if not result["edited"]:
            return {"outcomes": {acct.id: "nothing_to_change"}}
        try:
            url = call("open_pr", {"account": acct.to_dict(), "result": result, "summary": state.get("summary", "")})["pr_url"]
        except Exception as e:  # noqa: BLE001
            return fail(state, "open_pr", e)
        store.record_cleanup(CleanupRecord(acct.id, state["run_id"], now_iso(), result["edited"],
                                           result["savings_usd"], url["pr_url"] if isinstance(url, dict) else url,
                                           "proposed", state.get("summary", "")))
        return {"pr_urls": {acct.id: url}, "outcomes": {acct.id: "pr_open"}, "failed_step": None}

    def confirm_merge(state: RunState) -> dict:
        acct_id = state["current"]
        decision = interrupt({"type": "confirm_merge", "account_id": acct_id, "pr_url": state["pr_urls"][acct_id]})
        if not decision.get("merged"):
            return {"outcomes": {acct_id: "pr_open"}}
        return {"outcomes": {acct_id: "merged_pending_plan"}}

    def execute_node(state: RunState) -> dict:
        acct = accounts_by_id()[state["current"]]
        try:
            plan = call("execute", {"account": acct.to_dict()})
        except Exception as e:  # noqa: BLE001
            return fail(state, "execute", e)
        store.update_status(acct.id, state["run_id"], "merged")
        return {"plans": {acct.id: plan}, "outcomes": {acct.id: "merged"}, "failed_step": None}

    def handle_error(state: RunState) -> dict:
        acct_id = state["current"]
        decision = interrupt({"type": "handle_error", "account_id": acct_id, "step": state["failed_step"],
                              "error": state["errors"].get(acct_id, "")})
        if decision.get("action") == "retry":
            return {"errors": {acct_id: ""}}
        step = state["failed_step"]
        if step == "execute":
            try:
                store.update_status(acct_id, state["run_id"], "failed")
            except KeyError:
                pass
        return {"outcomes": {acct_id: f"skipped_after_{step}_error"}, "failed_step": "skipped"}

    # ---- routing -----------------------------------------------------------------
    def after_next(state: RunState) -> str:
        return END if state["current"] is None else "refactor"

    def route_failure(ok_target: str):
        def route(state: RunState) -> str:
            return "handle_error" if state.get("failed_step") in ("refactor", "open_pr", "execute") else ok_target
        return route

    def after_approve(state: RunState) -> str:
        if state.get("failed_step") == "refactor":
            return "handle_error"
        return "open_pr" if state["outcomes"].get(state["current"]) == "approved" else "next_account"

    def after_open_pr(state: RunState) -> str:
        if state.get("failed_step") == "open_pr":
            return "handle_error"
        return "confirm_merge" if state["outcomes"].get(state["current"]) == "pr_open" else "next_account"

    def after_confirm(state: RunState) -> str:
        return "execute" if state["outcomes"].get(state["current"]) == "merged_pending_plan" else "next_account"

    def after_error(state: RunState) -> str:
        if state.get("failed_step") == "skipped":
            return "next_account"
        return {"refactor": "refactor", "open_pr": "open_pr", "execute": "execute"}[state["failed_step"]]

    g = StateGraph(RunState)
    for name, fn in [("load", load), ("discover", discover_all), ("plan_queue", plan_queue),
                     ("next_account", next_account), ("refactor", refactor_node), ("approve_diff", approve_diff),
                     ("open_pr", open_pr_node), ("confirm_merge", confirm_merge), ("execute", execute_node),
                     ("handle_error", handle_error)]:
        g.add_node(name, fn)
    g.add_edge(START, "load")
    g.add_edge("load", "discover")
    g.add_edge("discover", "plan_queue")
    g.add_edge("plan_queue", "next_account")
    g.add_conditional_edges("next_account", after_next, ["refactor", END])
    g.add_conditional_edges("refactor", route_failure("approve_diff"), ["approve_diff", "handle_error"])
    g.add_conditional_edges("approve_diff", after_approve, ["open_pr", "next_account", "handle_error"])
    g.add_conditional_edges("open_pr", after_open_pr, ["confirm_merge", "next_account", "handle_error"])
    g.add_conditional_edges("confirm_merge", after_confirm, ["execute", "next_account"])
    g.add_conditional_edges("execute", route_failure("next_account"), ["next_account", "handle_error"])
    g.add_conditional_edges("handle_error", after_error, ["refactor", "open_pr", "execute", "next_account"])
    return g.compile(checkpointer=checkpointer)
