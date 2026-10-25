from costwarden.accounts import Account
from costwarden.store import Store


def account_rows(store: Store, accounts: list[Account]) -> list[dict]:
    rows = []
    for a in accounts:
        m = store.metrics(a.id)
        recs = store.list_cleanups(a.id)
        rows.append({
            "account_id": a.id, "name": a.name, "cleanups": m.cleanups,
            "cost_avoided_monthly": m.cost_avoided_monthly, "cost_avoided_cumulative": m.cost_avoided_cumulative,
            "open_prs": m.open_prs, "last_cleanup": recs[0].timestamp if recs else None,
        })
    return rows


def savings_trend(store: Store, account_id: str | None = None) -> list[tuple[str, float]]:
    """Cumulative monthly run-rate avoided by merged cleanups, by date."""
    merged = sorted((r for r in store.list_cleanups(account_id) if r.status == "merged"), key=lambda r: r.timestamp)
    total, out = 0.0, []
    for r in merged:
        total += r.monthly_savings_usd
        day = r.timestamp[:10]
        if out and out[-1][0] == day:
            out[-1] = (day, round(total, 2))
        else:
            out.append((day, round(total, 2)))
    return out
