from typing import Protocol

import yaml

from costwarden.accounts.models import Account


class Registry(Protocol):
    def list_accounts(self) -> list[Account]: ...


class StaticRegistry:
    def __init__(self, path: str):
        self.path = path

    def list_accounts(self) -> list[Account]:
        with open(self.path) as f:
            raw = yaml.safe_load(f) or {}
        accounts = [Account.from_dict(a) for a in raw.get("accounts", [])]
        ids = [a.id for a in accounts]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"Duplicate account ids: {sorted(dupes)}")
        return accounts


def load_accounts(path: str = "config/accounts.yaml") -> list[Account]:
    return StaticRegistry(path).list_accounts()
