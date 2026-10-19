import pytest

from agent import is_safe, run_sql


def test_allows_select_and_with():
    assert is_safe("SELECT 1")
    assert is_safe("with x as (select 1) select * from x;")


@pytest.mark.parametrize("sql", ["DELETE FROM orders", "DROP TABLE customers", "SELECT 1; DELETE FROM orders", "UPDATE orders SET is_late=0"])
def test_blocks_writes(sql):
    assert not is_safe(sql)
    with pytest.raises(ValueError):
        run_sql(sql)


def test_reads_data():
    assert run_sql("SELECT COUNT(*) FROM customers") == [(300,)]


def test_blocked_write_request_refuses_without_an_llm_call(monkeypatch):
    """A write request stops at the guard: fixed refusal, no retry, no LLM call."""
    import agent

    monkeypatch.setattr(agent, "llm", None)  # any LLM call here would raise
    state = {"question": "Delete all cancelled orders.", "sql": "DELETE FROM orders WHERE is_cancelled = 1"}
    state.update(agent.execute(state))
    assert state["blocked"] and not state["rows"]
    assert agent.route({**state, "attempts": 1, "max_attempts": 3}) == "answer"
    assert agent.answer(state)["answer"] == agent.REFUSAL["en"]


def test_refusal_follows_the_question_language(monkeypatch):
    import agent

    monkeypatch.setattr(agent, "llm", None)
    assert agent.answer({"question": "ما هو رقم جوال العميل؟", "rows": []})["answer"] == agent.REFUSAL["ar"]
    assert agent.answer({"question": "What is the phone number?", "rows": []})["answer"] == agent.REFUSAL["en"]
