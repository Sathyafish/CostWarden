import json
import time
from typing import Protocol

import boto3

from costwarden.agents.entry import Deps, handle
from costwarden.resilience import ToolError, with_retry


class Invoker(Protocol):
    def call(self, agent: str, payload: dict) -> dict: ...


class LocalInvoker:
    def __init__(self, deps: Deps | None = None):
        self.deps = deps or Deps()

    def call(self, agent: str, payload: dict) -> dict:
        return handle(agent, payload, self.deps)


class LambdaInvoker:
    """Calls the deployed agent Lambdas ({prefix}-{agent})."""

    def __init__(self, prefix: str = "costwarden", session: boto3.Session | None = None):
        self.prefix = prefix
        self.client = (session or boto3.Session()).client("lambda")

    def call(self, agent: str, payload: dict) -> dict:
        resp = self.client.invoke(FunctionName=f"{self.prefix}-{agent}", Payload=json.dumps(payload).encode())
        body = json.loads(resp["Payload"].read())
        if resp.get("FunctionError") or not body.get("ok"):
            raise ToolError(payload.get("account", {}).get("id", "?"), agent, str(body.get("error") or body))
        return body["data"]


def get_invoker(settings) -> Invoker:
    if settings.agent_runtime == "lambda":
        return LambdaInvoker(settings.agent_function_prefix, boto3.Session(region_name=settings.aws_region))
    return LocalInvoker(Deps(settings))


def call_with_retry(invoker: Invoker, agent: str, payload: dict, sleep=time.sleep) -> dict:
    return with_retry(lambda: invoker.call(agent, payload), sleep=sleep)
