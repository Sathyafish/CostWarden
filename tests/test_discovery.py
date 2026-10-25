import boto3

from costwarden.accounts import Account, get_session
from costwarden.agents.discovery import discover
from costwarden.tools import aws_checks

ACCT = Account(id="123456789012", name="t", sources=("aws",))


def sess():
    return get_session(ACCT)


def test_unattached_ebs(seeded_aws):
    f = aws_checks.check_unattached_ebs(sess(), ACCT.id)
    assert len(f) >= 1 and all(x.resource_type == "EbsVolume" for x in f)
    assert any(x.monthly_savings_usd == 10.0 for x in f)  # 100 GB gp2 at $0.10


def test_attached_volume_not_flagged(seeded_aws):
    ids = {x.resource_id for x in aws_checks.check_unattached_ebs(sess(), ACCT.id)}
    attached = [
        v["VolumeId"] for v in seeded_aws.describe_volumes()["Volumes"] if v["State"] == "in-use"
    ]
    assert attached and not ids & set(attached)


def test_unassociated_eip(seeded_aws):
    f = aws_checks.check_unassociated_eips(sess(), ACCT.id)
    assert len(f) >= 1 and f[0].monthly_savings_usd == 3.65


def test_idle_nat(seeded_aws):
    f = aws_checks.check_idle_nat_gateways(sess(), ACCT.id)
    assert len(f) == 1 and f[0].resource_type == "NatGateway"


def test_old_snapshots(seeded_aws):
    assert aws_checks.check_old_snapshots(sess(), ACCT.id, min_age_days=0)
    assert not aws_checks.check_old_snapshots(sess(), ACCT.id, min_age_days=90)


def test_discover_aggregates_and_tags_account(seeded_aws):
    f = discover(ACCT)
    types = {x.resource_type for x in f}
    assert {"EbsVolume", "ElasticIp", "NatGateway"} <= types
    assert all(x.account_id == ACCT.id for x in f)


def test_discover_cost_explorer_source():
    a = Account(id="111111111111", name="a", sources=("cost_explorer",), data_file="data/dummy_cost_explorer.json")
    f = discover(a)
    assert len(f) == 9
    assert {x.action for x in f} == {"release", "resize"}
    web = next(x for x in f if x.resource_id == "i-0a1b2c3d4e5f60001")
    assert (web.current, web.recommended, web.tf_address) == ("m5.2xlarge", "m5.large", "aws_instance.web_api")
    assert round(sum(x.monthly_savings_usd for x in discover(
        Account(id="222222222222", name="b", sources=("cost_explorer",), data_file="data/dummy_cost_explorer.json"))), 2) > 0


def test_cost_explorer_requires_data_file():
    import pytest
    with pytest.raises(ValueError):
        discover(Account(id="1", name="a", sources=("cost_explorer",)))
