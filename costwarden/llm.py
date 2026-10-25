import json
import re
from typing import Callable

from langchain_core.messages import AIMessage

from costwarden.config import Settings, load_settings


def default_fake_handler(prompt: str) -> str:
    """Deterministic stand-in for an LLM so tests and the offline demo run without a server."""
    if "Respond with JSON" in prompt and "tools" in prompt:
        q = prompt.lower().rsplit("question:", 1)[-1]
        if re.search(r"\b(last|latest|recent)\b", q):
            return json.dumps({"tool": "last_cleanup", "args": {}})
        if re.search(r"\b(status|open|pending|proposed|rejected|merged)\b", q):
            status = next((s for s in ("rejected", "merged", "proposed") if s in q), "proposed")
            return json.dumps({"tool": "cleanups_by_status", "args": {"status": status}})
        if re.search(r"\b(type|types|kind)\b", q):
            return json.dumps({"tool": "top_resource_types", "args": {}})
        return json.dumps({"tool": "savings_between", "args": {}})
    if "Respond with a JSON list of resource ids" in prompt:
        ids = re.findall(r"^- (\S+)", prompt, flags=re.M)
        return json.dumps(ids)
    return (
        "Low risk overall: changes are reversible through Terraform and limited to "
        "idle or oversized resources. Review resize changes for restart impact."
    )


class FakeLLM:
    """Minimal chat-model stand-in: `.invoke(prompt)` returns an AIMessage."""

    def __init__(self, responses: list[str] | None = None, handler: Callable[[str], str] | None = None):
        self._responses = list(responses or [])
        self._handler = handler or default_fake_handler
        self.calls: list[str] = []

    def invoke(self, prompt, *args, **kwargs) -> AIMessage:
        text = prompt if isinstance(prompt, str) else str(prompt)
        self.calls.append(text)
        if self._responses:
            return AIMessage(content=self._responses.pop(0))
        return AIMessage(content=self._handler(text))


def get_llm(settings: Settings | None = None, provider: str | None = None):
    s = settings or load_settings()
    p = (provider or s.llm_provider).lower()
    if p == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(base_url=s.ollama_base_url, model=s.llm_model, temperature=0)
    if p == "nebius":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=s.nebius_base_url,
            api_key=s.nebius_api_key or "missing",
            model=s.nebius_model,
            temperature=0,
        )
    if p == "fake":
        return FakeLLM()
    raise ValueError(f"Unknown LLM provider: {p}")


def llm_text(llm, prompt: str) -> str:
    out = llm.invoke(prompt)
    return out.content if hasattr(out, "content") else str(out)
