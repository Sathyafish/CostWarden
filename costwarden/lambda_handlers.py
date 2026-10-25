"""Lambda entry points.

- discover / refactor / open_pr / execute: one function per agent, payload in, {"ok", "data", "error"} out.
- supervisor: start / resume / status for a run (the UI calls this one).
"""
import json
import traceback

from costwarden.agents.entry import AGENTS, Deps, handle

_service = None


def _agent_handler(agent: str):
    def handler(event, context=None):
        try:
            return {"ok": True, "data": handle(agent, event, Deps()), "error": None}
        except Exception as e:  # noqa: BLE001 - always return a payload, never raise
            return {"ok": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    handler.__name__ = f"{agent}_handler"
    return handler


discover_handler = _agent_handler("discover")
refactor_handler = _agent_handler("refactor")
open_pr_handler = _agent_handler("open_pr")
execute_handler = _agent_handler("execute")


def _get_service():
    global _service
    if _service is None:
        from costwarden.runs import RunService

        _service = RunService()
    return _service


def supervisor_handler(event, context=None):
    """event: {"action": "start", "account_ids": [...]} | {"action": "resume", "run_id", "value"} |
    {"action": "status", "run_id"}"""
    try:
        svc = _get_service()
        action = event.get("action")
        if action == "start":
            run_id = svc.start(event.get("account_ids"))
            return {"ok": True, "data": svc.status(run_id), "error": None}
        if action == "resume":
            svc.resume(event["run_id"], event["value"])
            return {"ok": True, "data": svc.status(event["run_id"]), "error": None}
        if action == "status":
            return {"ok": True, "data": svc.status(event["run_id"]), "error": None}
        return {"ok": False, "data": None, "error": f"Unknown action: {action}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"}


__all__ = ["discover_handler", "refactor_handler", "open_pr_handler", "execute_handler", "supervisor_handler"]
