import os

from streamlit.testing.v1 import AppTest


def make_app(monkeypatch):
    monkeypatch.setenv("STORE_BACKEND", "memory")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("TF_SOURCE", "local")
    return AppTest.from_file(os.path.abspath("costwarden/ui/app.py"), default_timeout=30).run()


def test_app_renders_without_exception(monkeypatch):
    at = make_app(monkeypatch)
    assert not at.exception
    assert any("Cost avoided" in m.label for m in at.metric)


def test_run_flow_reaches_approval(monkeypatch):
    at = make_app(monkeypatch)
    next(b for b in at.button if b.label == "Start cleanup run").click().run()
    assert not at.exception
    assert any("Approve changes" in s.value for s in at.subheader)
    next(b for b in at.button if b.label == "Approve and open draft PR").click().run()
    assert any("Confirm merge" in s.value for s in at.subheader)
