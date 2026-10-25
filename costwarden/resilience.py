import time
from dataclasses import dataclass


@dataclass
class ToolError(Exception):
    account_id: str
    step: str
    message: str

    def __str__(self) -> str:
        return f"[{self.account_id}] {self.step}: {self.message}"


def with_retry(fn, *, attempts: int = 3, base_delay: float = 0.5, sleep=time.sleep):
    """Call fn(); on failure retry with exponential backoff, re-raising the last error."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - any tool failure is retried
            last = e
            if i < attempts - 1:
                sleep(base_delay * (2**i))
    assert last is not None
    raise last
