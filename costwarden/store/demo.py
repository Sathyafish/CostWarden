from datetime import datetime, timedelta, timezone

from costwarden.store import CleanupRecord, Store

# days ago, account, run, status, monthly savings, [(resource type, id, savings)]
HISTORY = [
    (75, "111111111111", "seed0001", "merged", 188.0,
     [("EbsVolume", "vol-0seed01", 100.0), ("ElasticIp", "eipalloc-0seed01", 3.65), ("EbsSnapshot", "snap-0seed01", 84.35)]),
    (48, "222222222222", "seed0002", "merged", 350.4, [("RdsDbInstance", "db-seed01", 350.4)]),
    (21, "111111111111", "seed0003", "merged", 210.24, [("EC2Instance", "i-0seed0003", 210.24)]),
    (9, "222222222222", "seed0004", "merged", 91.1, [("EC2Instance", "i-0seed0004", 91.1)]),
    (4, "111111111111", "seed0005", "rejected", 60.74, [("EC2Instance", "i-0seed0005", 60.74)]),
]


def seed_history(store: Store, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    for days, acct, run, status, sav, res in HISTORY:
        ts = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.record_cleanup(CleanupRecord(
            acct, run, ts,
            [{"resource_type": t, "resource_id": i, "monthly_savings_usd": s} for t, i, s in res],
            sav, f"https://github.com/example/costwarden-sandbox/pull/{run[-1]}", status, "Seeded demo history."))
    return len(HISTORY)
