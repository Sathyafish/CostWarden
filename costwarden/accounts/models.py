from dataclasses import asdict, dataclass, field, fields


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    role_arn: str | None = None
    region: str = "us-east-1"
    tf_path: str = ""
    repo: str = ""
    sources: tuple[str, ...] = ("aws",)
    data_file: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sources"] = list(self.sources)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in names}
        kw["id"] = str(kw["id"])
        if "sources" in kw:
            kw["sources"] = tuple(kw["sources"])
        return cls(**kw)
