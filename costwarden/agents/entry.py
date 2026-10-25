"""Agent entry points. Each takes and returns plain JSON-friendly dicts so the same function
runs in-process (local) or behind a Lambda handler."""
from dataclasses import dataclass, field

from costwarden.accounts import Account
from costwarden.agents.discovery import discover
from costwarden.agents.execution import run_plan
from costwarden.agents.refactor import refactor
from costwarden.agents.vcs import open_pull_request
from costwarden.config import Settings, load_settings
from costwarden.models import Finding
from costwarden.tools.github_client import FakeGitHubClient, GitHubClient, PyGithubClient
from costwarden.tools.tf_source import GitHubTfSource, LocalTfSource, TfSource


@dataclass
class Deps:
    settings: Settings = field(default_factory=load_settings)
    github: GitHubClient | None = None

    def github_client(self) -> GitHubClient:
        if self.github is None:
            s = self.settings
            if s.github_token and s.github_repo:
                self.github = PyGithubClient(s.github_token, s.github_repo, s.github_base_branch)
            else:
                self.github = FakeGitHubClient()
        return self.github

    def tf_source(self, account: Account) -> TfSource:
        if self.settings.tf_source == "github":
            return GitHubTfSource(self.github_client(), account.tf_path)
        return LocalTfSource(account.tf_path)


def discover_agent(payload: dict, deps: Deps) -> dict:
    account = Account.from_dict(payload["account"])
    return {"findings": [f.to_dict() for f in discover(account)]}


def refactor_agent(payload: dict, deps: Deps) -> dict:
    account = Account.from_dict(payload["account"])
    findings = [Finding.from_dict(f) for f in payload["findings"]]
    return refactor(findings, deps.tf_source(account))


def open_pr_agent(payload: dict, deps: Deps) -> dict:
    account = Account.from_dict(payload["account"])
    url = open_pull_request(account, payload["result"], payload.get("summary", ""), deps.github_client())
    return {"pr_url": url}


def execute_agent(payload: dict, deps: Deps) -> dict:
    return run_plan(Account.from_dict(payload["account"]))


AGENTS = {
    "discover": discover_agent,
    "refactor": refactor_agent,
    "open_pr": open_pr_agent,
    "execute": execute_agent,
}


def handle(agent: str, payload: dict, deps: Deps) -> dict:
    if agent not in AGENTS:
        raise ValueError(f"Unknown agent: {agent}")
    return AGENTS[agent](payload, deps)
