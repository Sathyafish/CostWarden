from costwarden.accounts import Account
from costwarden.agents.discovery import discover
from costwarden.agents.narrative import rank_findings, write_risk_summary
from costwarden.agents.refactor import refactor
from costwarden.agents.vcs import branch_name, build_pr_body, open_pull_request
from costwarden.llm import FakeLLM
from costwarden.tools.github_client import FakeGitHubClient
from costwarden.tools.tf_source import LocalTfSource

A = Account(id="111111111111", name="prototype", sources=("cost_explorer",),
            data_file="data/dummy_cost_explorer.json", tf_path="sample_terraform/account_a")


def result():
    return refactor(discover(A), LocalTfSource("sample_terraform/account_a"))


def test_branch_name_includes_date_and_account():
    assert branch_name(A, "2026-10-24") == "costwarden/cleanup-2026-10-24-111111111111"


def test_pr_is_draft_with_savings_and_resources():
    c = FakeGitHubClient()
    url = open_pull_request(A, result(), "low risk", c, today="2026-10-24")
    assert url.endswith("/pull/1")
    kinds = [x[0] for x in c.calls]
    assert kinds == ["create_branch", "commit_files", "open_pr"]
    _, _, title, body, draft = c.calls[2]
    assert draft is True and "$" in title and "vol-0c1d2e3f40001" in body and "low risk" in body


def test_pr_body_lists_unmapped():
    r = result()
    r["unmapped"] = [{"finding": {"resource_id": "vol-x"}, "reason": "No matching Terraform resource block"}]
    assert "vol-x" in build_pr_body(A, r, "")


def test_rank_applies_valid_order_and_ignores_unknown():
    f = discover(A)
    ids = [x.resource_id for x in f]
    llm = FakeLLM([f'["{ids[2]}", "bogus", "{ids[0]}"]'])
    ranked = rank_findings(llm, f)
    assert [x.resource_id for x in ranked[:2]] == [ids[2], ids[0]]
    assert len(ranked) == len(f)


def test_rank_preserves_all_findings_when_llm_returns_garbage():
    f = discover(A)
    assert rank_findings(FakeLLM(["not json at all"]), f) == f


def test_rank_survives_llm_exception():
    class Boom:
        def invoke(self, *_):
            raise ConnectionError("down")

    f = discover(A)
    assert rank_findings(Boom(), f) == f


def test_risk_summary_uses_llm_text():
    assert write_risk_summary(FakeLLM(["  fine  "]), "prototype", result()) == "fine"


def test_commit_paths_are_repo_relative():
    c = FakeGitHubClient()
    open_pull_request(A, result(), "", c)
    files = next(x for x in c.calls if x[0] == "commit_files")[2]
    assert list(files) == ["sample_terraform/account_a/main.tf"]


def test_github_tf_source_strips_prefix_and_fake_client_falls_back_to_local():
    from costwarden.tools.tf_source import GitHubTfSource

    files = GitHubTfSource(FakeGitHubClient(), "sample_terraform/account_a").files()
    assert list(files) == ["main.tf"] and "aws_instance" in files["main.tf"]
