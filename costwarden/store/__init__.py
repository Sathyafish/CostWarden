from typing import Protocol

from costwarden.config import Settings, load_settings
from costwarden.store.models import CleanupRecord, Metrics, compute_metrics, now_iso


class Store(Protocol):
    def record_cleanup(self, rec: CleanupRecord) -> None: ...
    def update_status(self, account_id: str, run_id: str, status: str) -> None: ...
    def list_cleanups(self, account_id: str | None = None, since: str | None = None) -> list[CleanupRecord]: ...
    def metrics(self, account_id: str | None = None) -> Metrics: ...


def get_store(settings: Settings | None = None) -> Store:
    s = settings or load_settings()
    if s.store_backend == "memory":
        from costwarden.store.memory import MemoryStore

        return MemoryStore()
    import boto3

    from costwarden.store.dynamo import DynamoStore

    return DynamoStore(s.dynamodb_table, boto3.Session(region_name=s.aws_region))


__all__ = ["Store", "CleanupRecord", "Metrics", "compute_metrics", "get_store", "now_iso"]
