import uuid

from langgraph.types import Command

from costwarden.agents.supervisor import build_graph
from costwarden.config import Settings, load_settings


class RunService:
    """Start, resume and inspect runs. Works the same locally and inside the supervisor Lambda:
    every call restores the thread's checkpoint first and persists it afterwards."""

    def __init__(self, settings: Settings | None = None, **graph_kwargs):
        self.settings = settings or load_settings()
        self.graph = build_graph(self.settings, **graph_kwargs)
        self.saver = self.graph.checkpointer

    @staticmethod
    def _cfg(run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    def start(self, account_ids: list[str] | None = None) -> str:
        run_id = uuid.uuid4().hex[:12]
        self.saver.restore(run_id)
        try:
            self.graph.invoke({"run_id": run_id, "account_ids": account_ids}, self._cfg(run_id))
        finally:
            self.saver.persist(run_id)
        return run_id

    def resume(self, run_id: str, value: dict) -> None:
        self.saver.restore(run_id)
        try:
            self.graph.invoke(Command(resume=value), self._cfg(run_id))
        finally:
            self.saver.persist(run_id)

    def status(self, run_id: str) -> dict:
        self.saver.restore(run_id)
        snap = self.graph.get_state(self._cfg(run_id))
        v = snap.values or {}
        pending = None
        for task in snap.tasks:
            for it in task.interrupts:
                pending = it.value
                break
        return {
            "run_id": run_id,
            "known": bool(v),
            "done": bool(v) and not snap.next,
            "pending": pending,
            "findings": {a: len(fs) for a, fs in v.get("findings", {}).items()},
            "errors": {a: e for a, e in v.get("errors", {}).items() if e},
            "outcomes": v.get("outcomes", {}),
            "pr_urls": v.get("pr_urls", {}),
            "plans": v.get("plans", {}),
        }
