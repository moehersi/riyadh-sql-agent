"""Text-to-SQL agent with a Reflexion loop (LangGraph).

generate SQL -> execute (read-only) -> on error: reflect, store a lesson, retry.
Lessons persist in lessons.json and are fed into future questions.
Whatever happens, the run ends at `answer`, which words the result (or the
refusal) in the language of the question.
"""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

load_dotenv()
ROOT = Path(__file__).parent
DB = ROOT / "riyadh.db"
LESSONS = ROOT / "lessons.json"

BACKEND = os.getenv("BACKEND", "gemini")
if BACKEND == "gemini":
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL", "gemini-flash-lite-latest"), temperature=0)
else:
    from langchain_ollama import ChatOllama
    llm = ChatOllama(model=os.getenv("MODEL", "llama3.2"), temperature=0)


REFUSAL = {
    "en": "I can't answer that from this data.",
    "ar": "لا أستطيع الإجابة من هذه البيانات.",
}


class State(TypedDict, total=False):
    question: str
    sql: str
    rows: list
    error: str
    answer: str
    blocked: bool
    attempts: int
    max_attempts: int
    use_lessons: bool


def lang(text: str) -> str:
    """'ar' if the text contains any Arabic letter, else 'en'."""
    return "ar" if any("\u0600" <= ch <= "\u06ff" for ch in text) else "en"


def schema() -> str:
    con = sqlite3.connect(DB)
    out = []
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        out.append(f"{t}({', '.join(cols)})")
    return "\n".join(out)


def load_lessons() -> list:
    return json.loads(LESSONS.read_text(encoding="utf-8")) if LESSONS.exists() else []


def is_safe(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    return bool(re.match(r"(?is)^\s*(select|with)\b", s)) and ";" not in s


def run_sql(sql: str) -> list:
    if not is_safe(sql):
        raise ValueError("only a single SELECT/WITH statement is allowed")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)  # read-only at the DB level too
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _text(content) -> str:
    """Normalize a chat response's .content: Gemini returns a list of parts, Ollama a plain str."""
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content


def generate(state: State) -> State:
    lessons = load_lessons() if state.get("use_lessons") else []
    # DELIBERATELY WEAKENED PROMPT - this branch exists only to prove the eval
    # harness catches a prompt regression. Do not merge.
    # Removed: the column names (table names only) and the storage-format hints.
    prompt = (
        "You write one SQLite query that answers the question.\n"
        f"Tables: {', '.join(line.split('(')[0] for line in schema().splitlines())}\n"
        + ("Lessons from past mistakes:\n- " + "\n- ".join(lessons) + "\n" if lessons else "")
        + (f"Your previous query:\n{state['sql']}\nfailed with: {state['error']}\n" if state.get("error") else "")
        + f"Question: {state['question']}\n"
        "Return only the SQL, no explanation, no code fences."
    )
    sql = _text(llm.invoke(prompt).content).strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    return {"sql": sql, "attempts": state.get("attempts", 0) + 1}


def execute(state: State) -> State:
    try:
        rows = run_sql(state["sql"])
        return {"rows": rows, "error": "" if rows else "query returned no rows"}
    except ValueError as e:  # the read-only guard refused it; a retry cannot help
        return {"rows": [], "error": str(e), "blocked": True}
    except Exception as e:
        return {"rows": [], "error": str(e)}


def reflect(state: State) -> State:
    lesson = _text(llm.invoke(
        f"Schema:\n{schema()}\nQuestion: {state['question']}\nSQL: {state['sql']}\nError: {state['error']}\n"
        "Write ONE short, general lesson (max 25 words) that would prevent this mistake on other questions. "
        "Return only the lesson."
    ).content).strip()
    lessons = load_lessons()
    if lesson not in lessons:
        LESSONS.write_text(json.dumps(lessons + [lesson], ensure_ascii=False, indent=2), encoding="utf-8")
    return {}


def answer(state: State) -> State:
    """Word the result in 1-2 sentences, in the question's language.

    With no rows there is nothing to word, so this returns the fixed refusal and
    spends no LLM call - and so can never invent a number out of an empty result.
    """
    rows = state.get("rows") or []
    if not rows:
        return {"answer": REFUSAL[lang(state["question"])]}
    text = _text(llm.invoke(
        f"Question: {state['question']}\n"
        f"SQL that produced the result:\n{state['sql']}\n"
        f"Result rows: {rows[:50]}\n"
        "Answer the question in 1-2 sentences, in the same language as the question. "
        "Use only numbers and names that appear in the result rows; invent nothing. "
        "Return only the answer."
    ).content).strip()
    return {"answer": text}


def route(state: State) -> str:
    if state.get("blocked") or not state["error"] or state["attempts"] >= state.get("max_attempts", 3):
        return "answer"
    return "reflect" if state.get("use_lessons") else "generate"


g = StateGraph(State)
g.add_node("generate", generate)
g.add_node("execute", execute)
g.add_node("reflect", reflect)
g.add_node("answer", answer)
g.set_entry_point("generate")
g.add_edge("generate", "execute")
g.add_conditional_edges("execute", route, {"reflect": "reflect", "generate": "generate", "answer": "answer"})
g.add_edge("reflect", "generate")
g.add_edge("answer", END)
graph = g.compile()


def ask(question: str, use_lessons=True, max_attempts=3) -> State:
    return graph.invoke({"question": question, "use_lessons": use_lessons, "max_attempts": max_attempts})


if __name__ == "__main__":
    out = ask(" ".join(sys.argv[1:]) or "Which district has the highest total order value?")
    print(out["sql"], "\n", out["rows"][:20], "\n", out["error"] or "ok", f"({out['attempts']} attempts)")
    print("\n" + out["answer"])
