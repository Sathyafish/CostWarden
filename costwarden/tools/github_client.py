from typing import Protocol


class GitHubClient(Protocol):
    def create_branch(self, name: str) -> None: ...
    def commit_files(self, branch: str, files: dict[str, str], message: str) -> None: ...
    def open_pr(self, branch: str, title: str, body: str, draft: bool = True) -> str: ...
    def read_tf_files(self, path: str) -> dict[str, str]: ...


class FakeGitHubClient:
    """Records calls; used in tests and when no GitHub token is configured."""

    def __init__(self, tf_files: dict[str, dict[str, str]] | None = None):
        self.calls: list[tuple] = []
        self._tf = tf_files or {}
        self._n = 0

    def create_branch(self, name: str) -> None:
        self.calls.append(("create_branch", name))

    def commit_files(self, branch: str, files: dict[str, str], message: str) -> None:
        self.calls.append(("commit_files", branch, dict(files), message))

    def open_pr(self, branch: str, title: str, body: str, draft: bool = True) -> str:
        self._n += 1
        self.calls.append(("open_pr", branch, title, body, draft))
        return f"https://github.com/example/costwarden-sandbox/pull/{self._n}"

    def read_tf_files(self, path: str) -> dict[str, str]:
        if path in self._tf:
            return {f"{path.rstrip('/')}/{p}": t for p, t in self._tf[path].items()}
        from costwarden.tools.tf_source import LocalTfSource

        # Fall back to the bundled sample Terraform so the demo works without a GitHub repo.
        return {f"{path.rstrip('/')}/{p}": t for p, t in LocalTfSource(path).files().items()}


class PyGithubClient:
    def __init__(self, token: str, repo: str, base: str = "main"):
        from github import Github

        self.repo = Github(token).get_repo(repo)
        self.base = base

    def create_branch(self, name: str) -> None:
        sha = self.repo.get_branch(self.base).commit.sha
        self.repo.create_git_ref(ref=f"refs/heads/{name}", sha=sha)

    def commit_files(self, branch: str, files: dict[str, str], message: str) -> None:
        for path, content in files.items():
            existing = self.repo.get_contents(path, ref=branch)
            self.repo.update_file(path, message, content, existing.sha, branch=branch)

    def open_pr(self, branch: str, title: str, body: str, draft: bool = True) -> str:
        return self.repo.create_pull(title=title, body=body, head=branch, base=self.base, draft=draft).html_url

    def read_tf_files(self, path: str) -> dict[str, str]:
        out: dict[str, str] = {}
        stack = [path]
        while stack:
            for item in self.repo.get_contents(stack.pop(), ref=self.base):
                if item.type == "dir":
                    stack.append(item.path)
                elif item.path.endswith(".tf"):
                    out[item.path] = item.decoded_content.decode()
        return out
