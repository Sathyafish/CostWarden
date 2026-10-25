from costwarden.accounts import Account
from costwarden.agents.discovery import discover
from costwarden.agents.refactor import map_to_terraform, refactor
from costwarden.models import Finding
from costwarden.tools import hcl
from costwarden.tools.tf_source import LocalTfSource

A = Account(id="111111111111", name="a", sources=("cost_explorer",), data_file="data/dummy_cost_explorer.json")
B = Account(id="222222222222", name="b", sources=("cost_explorer",), data_file="data/dummy_cost_explorer.json")
SRC_A = LocalTfSource("sample_terraform/account_a")
SRC_B = LocalTfSource("sample_terraform/account_b")


def test_maps_by_tf_address():
    f = next(x for x in discover(A) if x.resource_id == "vol-0c1d2e3f40001")
    t = map_to_terraform(f, SRC_A.files())
    assert t.address == "aws_ebs_volume.old_data" and t.file == "main.tf"


def test_maps_by_resource_id_fallback():
    files = {"x.tf": 'resource "aws_eip" "a" {\n  # eipalloc-123\n  domain = "vpc"\n}\n'}
    f = Finding("1", "ElasticIp", "eipalloc-123", "arn", "r", 3.65)
    assert map_to_terraform(f, files).address == "aws_eip.a"


def test_release_sets_count_zero_and_resize_sets_type():
    r = refactor(discover(A), SRC_A)
    new = r["files"]["main.tf"]
    assert "count = 0" in new and 'instance_type = "m5.large"' in new
    assert 'type = "gp3"' in new  # db_data gp2 -> gp3
    assert r["validation_ok"] and r["unmapped"] == []
    assert len(r["edited"]) == 9
    assert hcl.parses(new)


def test_refactor_does_not_write_files():
    before = SRC_A.files()
    refactor(discover(A), SRC_A)
    assert SRC_A.files() == before


def test_diff_is_unified_and_savings_sum():
    r = refactor(discover(B), SRC_B)
    assert r["diff"].startswith("--- a/main.tf") and "-  instance_class" in r["diff"]
    assert r["savings_usd"] == round(sum(e["monthly_savings_usd"] for e in r["edited"]), 2)


def test_unmapped_finding_reported_not_edited():
    ghost = Finding("1", "EbsVolume", "vol-nope", "arn", "r", 5.0, tf_address="aws_ebs_volume.ghost")
    r = refactor([ghost], SRC_A)
    assert r["files"] == {} and len(r["unmapped"]) == 1 and r["diff"] == ""


def test_resize_without_supported_attribute_is_unmapped():
    f = Finding("1", "ElasticIp", "x", "arn", "r", 1.0, action="resize", recommended="foo", tf_address="aws_eip.legacy")
    r = refactor([f], SRC_A)
    assert len(r["unmapped"]) == 1 and r["files"] == {}


def test_existing_count_is_overwritten():
    files = {"m.tf": 'resource "aws_eip" "a" {\n  count  = 1\n  domain = "vpc"\n}\n'}

    class Src:
        def files(self):
            return files

    f = Finding("1", "ElasticIp", "i", "arn", "r", 3.65, tf_address="aws_eip.a")
    r = refactor([f], Src())
    assert "count = 0" in r["files"]["m.tf"] and "count  = 1" not in r["files"]["m.tf"]
