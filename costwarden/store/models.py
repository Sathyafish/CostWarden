from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

STATUSES = ("proposed", "merged", "rejected", "failed")


@dataclass
class CleanupRecord:
    account_id: str
    run_id: str
    timestamp: str
    resources: list[dict] = field(default_factory=list)
    monthly_savings_usd: float = 0.0
    pr_url: str | None = None
    status: str = "proposed"
    summary: str = ""

    @property
    def ts_run(self) -> str:
        return f"{self.timestamp}#{self.run_id}"

    def to_dict(self) -> dict:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Metrics:
    cost_avoided_monthly: float
    cost_avoided_cumulative: float
    counts_by_status: dict
    by_resource_type: dict
    open_prs: int
    cleanups: int


def compute_metrics(records: list[CleanupRecord], now: datetime | None = None) -> Metrics:
    now = now or datetime.now(timezone.utc)
    merged = [r for r in records if r.status == "merged"]
    cumulative = 0.0
    for r in merged:
        ts = datetime.strptime(r.timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        cumulative += r.monthly_savings_usd * max((now - ts).days, 0) / 30
    counts = {s: 0 for s in STATUSES}
    by_type: dict[str, dict] = {}
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1
        if r.status != "merged":
            continue  # cost avoided by type counts merged cleanups only
        for res in r.resources:
            t = by_type.setdefault(res.get("resource_type", "unknown"), {"count": 0, "savings": 0.0})
            t["count"] += 1
            t["savings"] = round(t["savings"] + float(res.get("monthly_savings_usd", 0)), 2)
    return Metrics(
        cost_avoided_monthly=round(sum(r.monthly_savings_usd for r in merged), 2),
        cost_avoided_cumulative=round(cumulative, 2),
        counts_by_status=counts,
        by_resource_type=by_type,
        open_prs=counts.get("proposed", 0),
        cleanups=len(records),
    )
