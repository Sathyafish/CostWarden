from costwarden.store import Store


def _summary(rec) -> dict:
    return {
        "account_id": rec.account_id, "run_id": rec.run_id, "timestamp": rec.timestamp, "status": rec.status,
        "pr_url": rec.pr_url, "monthly_savings_usd": rec.monthly_savings_usd,
        "resources": [r.get("resource_id") for r in rec.resources],
    }


def last_cleanup(store: Store, account_id: str | None = None) -> dict | None:
    recs = store.list_cleanups(account_id)
    return _summary(recs[0]) if recs else None


def savings_between(store: Store, start: str | None = None, end: str | None = None,
                    account_id: str | None = None) -> dict:
    recs = [r for r in store.list_cleanups(account_id, since=start)
            if r.status == "merged" and (end is None or r.timestamp <= end)]
    return {"monthly_savings_usd": round(sum(r.monthly_savings_usd for r in recs), 2), "cleanups": len(recs),
            "start": start, "end": end, "account_id": account_id}


def cleanups_by_status(store: Store, status: str) -> list[dict]:
    return [_summary(r) for r in store.list_cleanups() if r.status == status]


def top_resource_types(store: Store, n: int = 3) -> list[dict]:
    by = store.metrics().by_resource_type
    ranked = sorted(by.items(), key=lambda kv: kv[1]["savings"], reverse=True)[:n]
    return [{"resource_type": k, **v} for k, v in ranked]
