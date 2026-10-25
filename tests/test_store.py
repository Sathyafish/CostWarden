from datetime import datetime, timezone

import boto3
import pytest

from costwarden.store import CleanupRecord, get_store
from costwarden.store.dynamo import DynamoStore
from costwarden.store.memory import MemoryStore
from costwarden.config import load_settings


def make_dynamo():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="t",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "account_id", "AttributeType": "S"},
                              {"AttributeName": "ts_run", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "account_id", "KeyType": "HASH"},
                   {"AttributeName": "ts_run", "KeyType": "RANGE"}],
    )
    return DynamoStore("t", boto3.Session(region_name="us-east-1"))


@pytest.fixture(params=["memory", "dynamo"])
def store(request, aws):
    return MemoryStore() if request.param == "memory" else make_dynamo()


def rec(acct="1", run="r1", ts="2026-10-01T00:00:00Z", sav=100.0, status="merged", rtype="EbsVolume"):
    return CleanupRecord(acct, run, ts, [{"resource_type": rtype, "monthly_savings_usd": sav}], sav,
                         "https://x/pr/1", status, "s")


def test_record_and_list_newest_first(store):
    store.record_cleanup(rec(run="a", ts="2026-10-01T00:00:00Z"))
    store.record_cleanup(rec(run="b", ts="2026-10-05T00:00:00Z"))
    assert [r.run_id for r in store.list_cleanups("1")] == ["b", "a"]


def test_filter_by_account_and_since(store):
    store.record_cleanup(rec(acct="1", run="a", ts="2026-10-01T00:00:00Z"))
    store.record_cleanup(rec(acct="2", run="b", ts="2026-10-10T00:00:00Z"))
    assert [r.run_id for r in store.list_cleanups("2")] == ["b"]
    assert [r.run_id for r in store.list_cleanups(since="2026-10-05T00:00:00Z")] == ["b"]


def test_update_status(store):
    store.record_cleanup(rec(status="proposed"))
    store.update_status("1", "r1", "merged")
    assert store.list_cleanups("1")[0].status == "merged"


def test_update_status_unknown_raises(store):
    with pytest.raises(KeyError):
        store.update_status("1", "nope", "merged")


def test_cost_avoided_counts_merged_only(store):
    store.record_cleanup(rec(run="a", sav=100, status="merged"))
    store.record_cleanup(rec(run="b", sav=50, status="proposed"))
    store.record_cleanup(rec(run="c", sav=25, status="rejected"))
    m = store.metrics("1")
    assert m.cost_avoided_monthly == 100 and m.open_prs == 1
    assert m.counts_by_status["rejected"] == 1 and m.cleanups == 3


def test_metrics_across_accounts_and_resource_types(store):
    store.record_cleanup(rec(acct="1", run="a", sav=10, rtype="EbsVolume"))
    store.record_cleanup(rec(acct="2", run="b", sav=30, rtype="RdsDbInstance"))
    m = store.metrics()
    assert m.cost_avoided_monthly == 40
    assert m.by_resource_type["RdsDbInstance"] == {"count": 1, "savings": 30.0}


def test_empty_store_metrics_are_zero(store):
    m = store.metrics()
    assert m.cost_avoided_monthly == 0 and m.cleanups == 0 and m.open_prs == 0


def test_cumulative_grows_with_age(store):
    store.record_cleanup(rec(sav=30, ts="2026-09-01T00:00:00Z"))
    from costwarden.store.models import compute_metrics
    m = compute_metrics(store.list_cleanups(), now=datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert m.cost_avoided_cumulative == 30.0


def test_get_store_memory_backend():
    s = load_settings(env={"STORE_BACKEND": "memory"})
    assert isinstance(get_store(s), MemoryStore)
