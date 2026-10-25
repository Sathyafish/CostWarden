import boto3
import pytest

from costwarden.agents.entry import Deps
from costwarden.agents.runtime import LocalInvoker
from costwarden.checkpoint import DynamoCheckpointer
from costwarden.config import load_settings
from costwarden.llm import FakeLLM
from costwarden.runs import RunService
from costwarden.store.memory import MemoryStore
from costwarden.tools.github_client import FakeGitHubClient
import costwarden.lambda_handlers as lh

SETTINGS = load_settings(env={"STORE_BACKEND": "memory", "LLM_PROVIDER": "fake"})


def make_table():
    boto3.client("dynamodb", region_name="us-east-1").create_table(
        TableName="cp", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "thread_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "thread_id", "KeyType": "HASH"}],
    )


def svc(gh, store):
    return RunService(SETTINGS, invoker=LocalInvoker(Deps(SETTINGS, gh)), store=store, llm=FakeLLM(),
                      checkpointer=DynamoCheckpointer("cp", boto3.Session(region_name="us-east-1")),
                      sleep=lambda _: None)


def test_dynamo_checkpoint_survives_new_process(aws):
    make_table()
    gh, store = FakeGitHubClient(), MemoryStore()
    run = svc(gh, store).start(["111111111111"])  # "invocation 1" stops at the approval gate
    assert svc(gh, store).status(run)["pending"]["type"] == "approve_diff"  # brand-new service, empty memory
    svc(gh, store).resume(run, {"approved": True})  # "invocation 2"
    svc(gh, store).resume(run, {"merged": True})  # "invocation 3"
    st = svc(gh, store).status(run)
    assert st["done"] and st["outcomes"]["111111111111"] == "merged"


def test_agent_handler_returns_payload_not_exception():
    out = lh.discover_handler({"account": {"id": "1", "name": "x", "sources": ["cost_explorer"]}})
    assert out["ok"] is False and "data_file" in out["error"]


def test_agent_handler_success():
    from costwarden.accounts import load_accounts

    a = load_accounts("config/accounts.yaml")[0]
    out = lh.discover_handler({"account": a.to_dict()})
    assert out["ok"] and len(out["data"]["findings"]) == 9


class StubService:
    def __init__(self):
        self.calls = []

    def start(self, account_ids=None):
        self.calls.append(("start", account_ids))
        return "r1"

    def resume(self, run_id, value):
        self.calls.append(("resume", run_id, value))

    def status(self, run_id):
        return {"run_id": run_id}


def test_supervisor_handler_actions(monkeypatch):
    stub = StubService()
    monkeypatch.setattr(lh, "_service", stub)
    assert lh.supervisor_handler({"action": "start", "account_ids": ["1"]}) == {
        "ok": True, "data": {"run_id": "r1"}, "error": None}
    assert lh.supervisor_handler({"action": "resume", "run_id": "r1", "value": {"approved": True}})["ok"]
    assert lh.supervisor_handler({"action": "status", "run_id": "r1"})["data"] == {"run_id": "r1"}
    bad = lh.supervisor_handler({"action": "nope"})
    assert bad["ok"] is False and "Unknown action" in bad["error"]
    assert stub.calls == [("start", ["1"]), ("resume", "r1", {"approved": True})]


def test_supervisor_handler_returns_error_payload_on_exception(monkeypatch):
    class Boom(StubService):
        def status(self, run_id):
            raise RuntimeError("table missing")

    monkeypatch.setattr(lh, "_service", Boom())
    out = lh.supervisor_handler({"action": "status", "run_id": "x"})
    assert out["ok"] is False and "table missing" in out["error"]
