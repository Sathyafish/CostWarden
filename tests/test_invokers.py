import io
import json

import pytest

from costwarden.agents.runtime import LambdaInvoker
from costwarden.client import LambdaClient
from costwarden.resilience import ToolError


class StubLambda:
    def __init__(self, body, function_error=None):
        self.body, self.function_error, self.calls = body, function_error, []

    def invoke(self, FunctionName, Payload):
        self.calls.append((FunctionName, json.loads(Payload)))
        out = {"Payload": io.BytesIO(json.dumps(self.body).encode())}
        if self.function_error:
            out["FunctionError"] = self.function_error
        return out


def make(cls, stub, *args):
    obj = cls.__new__(cls)
    obj.client = stub
    if cls is LambdaInvoker:
        obj.prefix = args[0]
    else:
        obj.name = args[0]
    return obj


def test_lambda_invoker_calls_prefixed_function_and_unwraps_data():
    stub = StubLambda({"ok": True, "data": {"findings": []}, "error": None})
    inv = make(LambdaInvoker, stub, "costwarden")
    assert inv.call("discover", {"account": {"id": "1"}}) == {"findings": []}
    assert stub.calls[0][0] == "costwarden-discover"


def test_lambda_invoker_raises_tool_error_on_not_ok():
    inv = make(LambdaInvoker, StubLambda({"ok": False, "data": None, "error": "boom"}), "costwarden")
    with pytest.raises(ToolError, match="boom"):
        inv.call("refactor", {"account": {"id": "7"}})


def test_lambda_invoker_raises_on_function_error():
    inv = make(LambdaInvoker, StubLambda({"errorMessage": "timeout"}, function_error="Unhandled"), "costwarden")
    with pytest.raises(ToolError):
        inv.call("execute", {"account": {"id": "7"}})


def test_lambda_client_start_resume_status():
    stub = StubLambda({"ok": True, "data": {"run_id": "r"}, "error": None})
    c = make(LambdaClient, stub, "costwarden-supervisor")
    assert c.start(["1"]) == {"run_id": "r"}
    c.resume("r", {"approved": True})
    c.status("r")
    assert [x[1]["action"] for x in stub.calls] == ["start", "resume", "status"]
    assert stub.calls[1][1]["value"] == {"approved": True}


def test_lambda_client_raises_on_error_payload():
    c = make(LambdaClient, StubLambda({"ok": False, "data": None, "error": "bad"}), "x")
    with pytest.raises(RuntimeError, match="bad"):
        c.status("r")
