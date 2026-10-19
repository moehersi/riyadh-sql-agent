# Riyadh SQL Agent: Text-to-SQL with Reflexion (LangGraph)

Ask a business question in **English or Arabic** about a Riyadh food-delivery market dataset. The agent writes SQL and runs it read-only. When a query fails, it writes a short **lesson** about the mistake, stores it, and retries. Stored lessons are reused on later questions (the Reflexion pattern).

## Architecture

```mermaid
graph TD;
	__start__([start]) --> generate;
	generate --> execute;
	execute -.ok / out of attempts.-> __end__([end]);
	execute -.error, no memory.-> generate;
	execute -.error, Reflexion.-> reflect;
	reflect -->|lesson saved to lessons.json| generate;
```

- **generate**: the LLM writes one SQLite query from the schema, any stored lessons, and the previous error.
- **execute**: runs the query in a read-only connection (`mode=ro`) and blocks anything that isn't a single SELECT/WITH. Errors and empty results are both counted as failures.
- **reflect**: the LLM turns the failure into one general lesson and saves it to `lessons.json`.

## Data

The Riyadh delivery market dataset (star schema): `customers` (300), `orders` (292), `dates` (768), `competitors` (30 POIs across HungerStation, Jahez, Marn and others). `data/` holds the audited, fixed version of this data (see the `Riyadh_Market_Project` repo for the full audit trail) — `is_late`, lat/lon, and `has_order_history` are all correct as of 2026-10-19.

## Results

The eval set is 20 questions (17 English, 3 Arabic), each with a known-correct SQL answer in `questions.json`. `python eval.py` writes `results.md`.

| Mode | Accuracy | Avg attempts |
|---|---|---|
| Baseline (1 try, no lessons) | _run eval.py_ | |
| Reflexion (3 tries + lessons) | _run eval.py_ | |

## Run

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
ollama pull llama3.2                             # one-time, local model, no API key
python load_db.py                                # builds riyadh.db
python agent.py "Which district has the highest total order value?"
python agent.py "ما الحي الذي فيه أكبر عدد من الطلبات؟"
python eval.py                                   # baseline vs Reflexion
pytest -q                                        # safety tests
```

Needs `ollama serve` running in the background (the Ollama app does this
automatically once installed). To use a different local model, set
`MODEL=<name>` in `.env` (copy `.env.example` first).

## Responsible AI

- Read-only at two levels: a SQL allow-list and a read-only database connection.
- The agent never changes data, and the safety tests prove it (`tests/test_guard.py`).
- Known limits: the scoring is lenient (extra columns in an answer are accepted), and the dataset is small. See `eval.py`.

## Stack

Python, LangGraph, LangChain (Ollama, local), SQLite, pytest.
