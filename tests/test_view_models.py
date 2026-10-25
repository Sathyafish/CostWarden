from costwarden.accounts import Account
from costwarden.store import CleanupRecord
from costwarden.store.memory import MemoryStore
from costwarden.ui.view_models import account_rows, savings_trend


def store():
    s = MemoryStore()
    for acct, run, ts, sav, st in [("1", "a", "2026-10-01T00:00:00Z", 100, "merged"),
                                   ("1", "b", "2026-10-01T12:00:00Z", 50, "merged"),
                                   ("1", "c", "2026-10-09T00:00:00Z", 25, "merged"),
                                   ("1", "d", "2026-10-10T00:00:00Z", 999, "proposed")]:
        s.record_cleanup(CleanupRecord(acct, run, ts, [], float(sav), None, st, ""))
    return s


ACCTS = [Account(id="1", name="one"), Account(id="2", name="two")]


def test_account_rows_totals():
    rows = account_rows(store(), ACCTS)
    assert rows[0]["cost_avoided_monthly"] == 175 and rows[0]["open_prs"] == 1 and rows[0]["cleanups"] == 4
    assert rows[0]["last_cleanup"] == "2026-10-10T00:00:00Z"


def test_account_without_cleanups_shows_zeros():
    r = account_rows(store(), ACCTS)[1]
    assert (r["cleanups"], r["cost_avoided_monthly"], r["open_prs"], r["last_cleanup"]) == (0, 0, 0, None)


def test_trend_is_cumulative_date_ordered_merged_only():
    assert savings_trend(store(), "1") == [("2026-10-01", 150.0), ("2026-10-09", 175.0)]


def test_trend_empty():
    assert savings_trend(MemoryStore()) == []
