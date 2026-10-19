"""Compare accuracy: baseline (1 attempt, no lessons) vs Reflexion (3 attempts + stored lessons).

Writes results.md.
"""
import json
import time

import agent

QUESTIONS = json.loads((agent.ROOT / "questions.json").read_text(encoding="utf-8"))


def norm(rows):
    return sorted(([round(v, 2) if isinstance(v, float) else v for v in r] for r in rows), key=str)


def correct(pred, gold) -> bool:
    # ponytail: lenient match - same row count, each gold row's values found in the predicted row
    # (lets the agent return extra columns). Swap for exact match if you want a stricter score.
    p, g = norm(pred), norm(gold)
    return len(p) == len(g) and all(set(map(str, gr)) <= set(map(str, pr)) for gr, pr in zip(g, p))


def run(use_lessons: bool, max_attempts: int):
    score, attempts, t0 = 0, 0, time.time()
    for item in QUESTIONS:
        out = agent.ask(item["q"], use_lessons, max_attempts)
        ok = correct(out.get("rows", []), agent.run_sql(item["sql"]))
        score += ok
        attempts += out["attempts"]
        print(("PASS" if ok else "FAIL"), item["q"][:70])
    return score, attempts, time.time() - t0


if __name__ == "__main__":
    agent.LESSONS.unlink(missing_ok=True)  # start Reflexion with an empty memory
    n = len(QUESTIONS)
    base = run(use_lessons=False, max_attempts=1)
    refl = run(use_lessons=True, max_attempts=3)
    table = (
        "| Mode | Accuracy | Avg attempts | Time (s) |\n|---|---|---|---|\n"
        f"| Baseline (1 try, no lessons) | {base[0]}/{n} ({base[0] / n:.0%}) | {base[1] / n:.2f} | {base[2]:.0f} |\n"
        f"| Reflexion (3 tries + lessons) | {refl[0]}/{n} ({refl[0] / n:.0%}) | {refl[1] / n:.2f} | {refl[2]:.0f} |\n"
    )
    (agent.ROOT / "results.md").write_text(f"# Results ({agent.llm.model})\n\n{table}", encoding="utf-8")
    print("\n" + table)
