from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class Finding:
    account_id: str
    resource_type: str
    resource_id: str
    arn: str
    reason: str
    monthly_savings_usd: float
    severity: str = "low"
    action: str = "release"  # release | resize
    current: str | None = None
    recommended: str | None = None
    tf_address: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})
