"""How the UI talks to the supervisor: in-process (local) or through the supervisor Lambda."""
import json
from typing import Protocol

import boto3

from costwarden.config import Settings, load_settings


class RunClient(Protocol):
    def start(self, account_ids: list[str] | None = None) -> dict: ...
    def resume(self, run_id: str, value: dict) -> dict: ...
    def status(self, run_id: str) -> dict: ...


class LocalClient:
    def __init__(self, service):
        self.service = service

    def start(self, account_ids=None) -> dict:
        return self.service.status(self.service.start(account_ids))

    def resume(self, run_id: str, value: dict) -> dict:
        self.service.resume(run_id, value)
        return self.service.status(run_id)

    def status(self, run_id: str) -> dict:
        return self.service.status(run_id)


class LambdaClient:
    def __init__(self, function_name: str, session: boto3.Session | None = None):
        self.name = function_name
        self.client = (session or boto3.Session()).client("lambda")

    def _call(self, event: dict) -> dict:
        resp = self.client.invoke(FunctionName=self.name, Payload=json.dumps(event).encode())
        body = json.loads(resp["Payload"].read())
        if not body.get("ok"):
            raise RuntimeError(body.get("error") or str(body))
        return body["data"]

    def start(self, account_ids=None) -> dict:
        return self._call({"action": "start", "account_ids": account_ids})

    def resume(self, run_id: str, value: dict) -> dict:
        return self._call({"action": "resume", "run_id": run_id, "value": value})

    def status(self, run_id: str) -> dict:
        return self._call({"action": "status", "run_id": run_id})


def get_client(settings: Settings | None = None, store=None) -> RunClient:
    s = settings or load_settings()
    if s.agent_runtime == "lambda":
        return LambdaClient(f"{s.agent_function_prefix}-supervisor", boto3.Session(region_name=s.aws_region))
    from costwarden.runs import RunService

    return LocalClient(RunService(s, store=store) if store is not None else RunService(s))
