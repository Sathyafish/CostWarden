import pytest

from costwarden.accounts import Account
from costwarden.agents.entry import Deps
from costwarden.agents.runtime import LocalInvoker
from costwarden.checkpoint import LocalCheckpointer
from costwarden.config import load_settings
from costwarden.llm import FakeLLM
from costwarden.resilience import ToolError
from costwarden.runs import RunService
from costwarden.store.memory import MemoryStore
from costwarden.tools.github_client import FakeGitHubClient

SETTINGS = load_settings(env={"STORE_BACKEND": "memory", "LLM_PROVIDER": "fake"})


class Harness:
    def __init__(self, invoker=None, registry=None):
        self.gh = FakeGitHubClient()
        self.store = MemoryStore()
        self.svc = RunService(
            SETTINGS, invoker=invoker or LocalInvoker(Deps(SETTINGS, self.gh)), store=self.store,
            llm=FakeLLM(), checkpointer=LocalCheckpointer(), sleep=lambda _: None,
            **({"registry": registry} if registry else {}),
        )


def approve(h, run, **kw):
    h.svc.resume(run, {"approved": True, **kw})


def test_graph_pauses_before_pr_with_diff():
    h = Harness()
    run = h.svc.start()
    st = h.svc.status(run)
    assert st["pending"]["type"] == "approve_diff" and st["pending"]["account_id"] == "111111111111"
    assert "count" in st["pending"]["diff"] and st["pending"]["savings_usd"] > 0
    assert h.gh.calls == []  # nothing written yet


def test_approve_opens_pr_then_pauses_for_merge_and_records_proposed():
    h = Harness()
    run = h.svc.start()
    approve(h, run)
    st = h.svc.status(run)
    assert st["pending"]["type"] == "confirm_merge" and st["pr_urls"]["111111111111"].endswith("/pull/1")
    assert [r.status for r in h.store.list_cleanups("111111111111")] == ["proposed"]


def test_full_happy_path_both_accounts():
    h = Harness()
    run = h.svc.start()
    for _ in range(2):
        approve(h, run)
        h.svc.resume(run, {"merged": True})
    st = h.svc.status(run)
    assert st["done"] and st["pending"] is None
    assert st["outcomes"] == {"111111111111": "merged", "222222222222": "merged"}
    assert h.store.metrics().cost_avoided_monthly > 1000
    assert all(p["ok"] for p in st["plans"].values())


def test_reject_pushes_nothing_and_never_executes():
    h = Harness()
    run = h.svc.start(["111111111111"])
    h.svc.resume(run, {"approved": False})
    st = h.svc.status(run)
    assert st["done"] and st["outcomes"]["111111111111"] == "rejected"
    assert h.gh.calls == [] and st["plans"] == {}
    assert h.store.list_cleanups()[0].status == "rejected"


def test_exclude_removes_finding_from_pr():
    h = Harness()
    run = h.svc.start(["111111111111"])
    approve(h, run, exclude=["vol-0c1d2e3f40001"])
    _, _, files, _ = next(c for c in h.gh.calls if c[0] == "commit_files")
    assert "old_data" in next(iter(files.values()))  # block still present
    body = next(c for c in h.gh.calls if c[0] == "open_pr")[3]
    assert "vol-0c1d2e3f40001" not in body


def test_merge_not_confirmed_leaves_pr_open():
    h = Harness()
    run = h.svc.start(["111111111111"])
    approve(h, run)
    h.svc.resume(run, {"merged": False})
    st = h.svc.status(run)
    assert st["done"] and st["outcomes"]["111111111111"] == "pr_open" and st["plans"] == {}


def test_resume_after_restart_uses_checkpoint():
    shared = LocalCheckpointer()
    gh, store = FakeGitHubClient(), MemoryStore()

    def svc():
        return RunService(SETTINGS, invoker=LocalInvoker(Deps(SETTINGS, gh)), store=store, llm=FakeLLM(),
                          checkpointer=shared, sleep=lambda _: None)

    run = svc().start(["111111111111"])
    svc().resume(run, {"approved": True})  # a brand-new graph object on the same checkpointer
    assert svc().status(run)["pending"]["type"] == "confirm_merge"


def test_zero_findings_ends_cleanly(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"rightsizing": {"RightsizingRecommendations": []}, "optimizationHub": {"items": []}}')
    acct = Account(id="9", name="empty", sources=("cost_explorer",), data_file=str(p), tf_path="sample_terraform/account_a")
    h = Harness(registry=lambda: [acct])
    run = h.svc.start()
    st = h.svc.status(run)
    assert st["done"] and st["pending"] is None and st["outcomes"] == {"9": "no_findings"}
    assert h.gh.calls == []


class FailingDiscover(LocalInvoker):
    def __init__(self, deps, bad):
        super().__init__(deps)
        self.bad = bad

    def call(self, agent, payload):
        if agent == "discover" and payload["account"]["id"] == self.bad:
            raise ToolError(self.bad, "discover", "sts denied")
        return super().call(agent, payload)


def test_one_account_failure_does_not_stop_others():
    h = Harness(invoker=FailingDiscover(Deps(SETTINGS, FakeGitHubClient()), "111111111111"))
    run = h.svc.start()
    st = h.svc.status(run)
    assert "sts denied" in st["errors"]["111111111111"]
    assert st["outcomes"]["111111111111"] == "discovery_failed"
    assert st["pending"]["account_id"] == "222222222222"


class FlakyExecute(LocalInvoker):
    def __init__(self, deps, fail_times):
        super().__init__(deps)
        self.left = fail_times

    def call(self, agent, payload):
        if agent == "execute" and self.left:
            self.left -= 1
            raise RuntimeError("plan backend down")
        return super().call(agent, payload)


def test_tool_failure_hands_off_to_human_then_retry_succeeds():
    h = Harness(invoker=FlakyExecute(Deps(SETTINGS, FakeGitHubClient()), fail_times=3))
    run = h.svc.start(["111111111111"])
    approve(h, run)
    h.svc.resume(run, {"merged": True})
    st = h.svc.status(run)
    assert st["pending"]["type"] == "handle_error" and st["pending"]["step"] == "execute"
    h.svc.resume(run, {"action": "retry"})
    st = h.svc.status(run)
    assert st["done"] and st["outcomes"]["111111111111"] == "merged"


def test_skip_after_error_marks_failed():
    h = Harness(invoker=FlakyExecute(Deps(SETTINGS, FakeGitHubClient()), fail_times=99))
    run = h.svc.start(["111111111111"])
    approve(h, run)
    h.svc.resume(run, {"merged": True})
    h.svc.resume(run, {"action": "skip"})
    st = h.svc.status(run)
    assert st["done"] and h.store.list_cleanups()[0].status == "failed"


def test_llm_down_does_not_crash_run():
    class Boom:
        def invoke(self, *_):
            raise ConnectionError("ollama unreachable")

    gh = FakeGitHubClient()
    svc = RunService(SETTINGS, invoker=LocalInvoker(Deps(SETTINGS, gh)), store=MemoryStore(), llm=Boom(),
                     checkpointer=LocalCheckpointer(), sleep=lambda _: None)
    run = svc.start(["111111111111"])
    st = svc.status(run)
    assert st["pending"]["type"] == "approve_diff"
    assert "unavailable" in st["pending"]["summary"]
