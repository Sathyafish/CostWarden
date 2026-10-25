from pathlib import Path
from typing import Protocol


class TfSource(Protocol):
    def files(self) -> dict[str, str]:
        """Return {relative path: text} for every .tf file."""
        ...


class LocalTfSource:
    def __init__(self, root: str):
        self.root = Path(root)

    def files(self) -> dict[str, str]:
        return {
            str(p.relative_to(self.root)): p.read_text()
            for p in sorted(self.root.rglob("*.tf"))
        }


class GitHubTfSource:
    """Reads .tf files under `path` of a GitHub repo (used when running on Lambda).
    Keys are relative to `path`, like LocalTfSource."""

    def __init__(self, client, path: str):
        self.client = client
        self.path = path

    def files(self) -> dict[str, str]:
        prefix = self.path.rstrip("/") + "/"
        return {p[len(prefix):] if p.startswith(prefix) else p: t
                for p, t in self.client.read_tf_files(self.path).items()}
