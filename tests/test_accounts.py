import boto3
import pytest

from costwarden.accounts import Account, get_session, load_accounts


def write(tmp_path, text):
    p = tmp_path / "a.yaml"
    p.write_text(text)
    return str(p)


def test_load_accounts_single(tmp_path):
    p = write(tmp_path, "accounts:\n  - id: '1'\n    name: a\n")
    accts = load_accounts(p)
    assert len(accts) == 1 and accts[0].role_arn is None and accts[0].sources == ("aws",)


def test_load_accounts_many_order_preserved(tmp_path):
    p = write(tmp_path, "accounts:\n  - {id: '2', name: b}\n  - {id: '1', name: a}\n")
    assert [a.id for a in load_accounts(p)] == ["2", "1"]


def test_duplicate_ids_rejected(tmp_path):
    p = write(tmp_path, "accounts:\n  - {id: '1', name: a}\n  - {id: '1', name: b}\n")
    with pytest.raises(ValueError):
        load_accounts(p)


def test_repo_accounts_file_loads():
    assert len(load_accounts("config/accounts.yaml")) == 2


def test_account_dict_roundtrip():
    a = Account(id="1", name="a", sources=("aws", "cost_explorer"))
    assert Account.from_dict(a.to_dict()) == a


def test_get_session_default_when_no_role():
    s = get_session(Account(id="1", name="a", region="eu-west-1"))
    assert s.region_name == "eu-west-1"


def test_get_session_assumes_role(aws):
    role = boto3.client("iam").create_role(
        RoleName="CostWardenReadOnly", AssumeRolePolicyDocument="{}"
    )["Role"]["Arn"]
    s = get_session(Account(id="1", name="a", role_arn=role))
    creds = s.get_credentials()
    assert creds.access_key != "testing"
