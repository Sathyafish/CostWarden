from costwarden.agents.qa import HELP, answer
from costwarden.llm import FakeLLM
from costwarden.store import CleanupRecord
from costwarden.store.memory import MemoryStore


def seeded():
    s = MemoryStore()
    s.record_cleanup(CleanupRecord("1", "a", "2026-10-01T00:00:00Z",
                                   [{"resource_id": "vol-1", "resource_type": "EbsVolume", "monthly_savings_usd": 50}],
                                   50.0, "https://pr/1", "merged", ""))
    s.record_cleanup(CleanupRecord("2", "b", "2026-10-20T00:00:00Z",
                                   [{"resource_id": "i-9", "resource_type": "EC2Instance", "monthly_savings_usd": 210.24}],
                                   210.24, "https://pr/2", "proposed", ""))
    return s


def test_last_cleanup_question_uses_tool_and_exact_numbers():
    a = answer("what was the last cleanup and how much cost was avoided?", seeded(), FakeLLM())
    assert a.tool == "last_cleanup"
    assert "$210.24" in a.text and "https://pr/2" in a.text and "not yet merged" in a.text


def test_savings_sums_merged_only():
    a = answer("how much have we saved in total?", seeded(), FakeLLM())
    assert a.tool == "savings_between" and "$50.00" in a.text and "$260.24" not in a.text


def test_explicit_tool_call_with_account_filter():
    llm = FakeLLM(['{"tool": "last_cleanup", "args": {"account_id": "1"}}'])
    a = answer("anything", seeded(), llm)
    assert "$50.00" in a.text and "avoids" in a.text


def test_status_question():
    a = answer("which cleanups are still proposed?", seeded(), FakeLLM())
    assert a.tool == "cleanups_by_status" and "https://pr/2" in a.text


def test_top_resource_types():
    a = answer("which resource types save the most?", seeded(), FakeLLM())
    assert a.tool == "top_resource_types" and a.text.index("EC2Instance") < a.text.index("EbsVolume")


def test_empty_store_does_not_invent_numbers():
    a = answer("what was the last cleanup?", MemoryStore(), FakeLLM())
    assert "no cleanups" in a.text.lower() and "$" not in a.text


def test_unparseable_llm_output_returns_help():
    assert answer("x", seeded(), FakeLLM(["I think maybe"])).text == HELP


def test_unknown_tool_rejected():
    assert answer("x", seeded(), FakeLLM(['{"tool": "drop_table", "args": {}}'])).text == HELP


def test_unknown_account_message():
    a = answer("x", seeded(), FakeLLM(['{"tool": "last_cleanup", "args": {"account_id": "999"}}']))
    assert "999" in a.text and "$" not in a.text


def test_llm_down_returns_help():
    class Boom:
        def invoke(self, *_):
            raise ConnectionError("down")

    assert answer("x", seeded(), Boom()).text == HELP


def test_bad_args_return_help():
    llm = FakeLLM(['{"tool": "top_resource_types", "args": {"n": "many"}}'])
    assert answer("x", seeded(), llm).text == HELP
