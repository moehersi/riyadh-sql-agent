"""Load the Riyadh delivery CSVs into a SQLite database (riyadh.db)."""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "riyadh.db"
TABLES = {
    "customers": "dim_customer.csv",
    "dates": "dim_date.csv",
    "orders": "fact_order.csv",
    "competitors": "competitors_clean.csv",
}


def cast(v):
    if v in ("True", "False"):
        return int(v == "True")
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    return v


def main():
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    for table, file in TABLES.items():
        with open(ROOT / "data" / file, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        # column names: lowercase, spaces -> underscores ("Total Days" -> total_days)
        cols = [c.strip().lower().replace(" ", "_") for c in rows[0]]
        con.execute(f"CREATE TABLE {table} ({', '.join(cols)})")
        con.executemany(
            f"INSERT INTO {table} VALUES ({', '.join('?' * len(cols))})",
            [[cast(v) for v in r] for r in rows[1:]],
        )
        print(f"{table}: {len(rows) - 1} rows")
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
