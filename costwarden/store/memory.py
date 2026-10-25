from costwarden.store.models import CleanupRecord, Metrics, compute_metrics


class MemoryStore:
    def __init__(self):
        self._items: dict[tuple[str, str], CleanupRecord] = {}

    def record_cleanup(self, rec: CleanupRecord) -> None:
        self._items[(rec.account_id, rec.ts_run)] = rec

    def update_status(self, account_id: str, run_id: str, status: str) -> None:
        for (acct, _), rec in self._items.items():
            if acct == account_id and rec.run_id == run_id:
                rec.status = status
                return
        raise KeyError(f"No cleanup for {account_id}/{run_id}")

    def list_cleanups(self, account_id: str | None = None, since: str | None = None) -> list[CleanupRecord]:
        recs = [
            r for r in self._items.values()
            if (account_id is None or r.account_id == account_id) and (since is None or r.timestamp >= since)
        ]
        return sorted(recs, key=lambda r: r.timestamp, reverse=True)

    def metrics(self, account_id: str | None = None) -> Metrics:
        return compute_metrics(self.list_cleanups(account_id))
