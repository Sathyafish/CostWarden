import pytest

from costwarden.config import load_settings
from costwarden.llm import FakeLLM, get_llm


def test_ollama_default():
    s = load_settings(env={})
    llm = get_llm(s)
    assert type(llm).__name__ == "ChatOllama"
    assert llm.base_url == "http://10.135.128.9:11434"
    assert llm.model == "llama3.1"


def test_nebius_provider():
    s = load_settings(env={"NEBIUS_API_KEY": "k"})
    llm = get_llm(s, provider="nebius")
    assert type(llm).__name__ == "ChatOpenAI"
    assert "nebius" in str(llm.openai_api_base)


def test_fake_provider_canned_response():
    llm = FakeLLM(["hello"])
    assert llm.invoke("x").content == "hello"


def test_get_llm_fake():
    assert isinstance(get_llm(provider="fake"), FakeLLM)


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_llm(provider="nope")
