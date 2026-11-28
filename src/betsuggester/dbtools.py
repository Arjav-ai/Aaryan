"""Save / restore the database as plain text so it can live in git without bloating the repo
(each refresh only appends a few lines, which git stores as a tiny change).

Usage: python -m betsuggester.dbtools dump | restore
"""
import sqlite3
import sys
from pathlib import Path

from .db import DB_PATH

DUMP = Path("data/db_dump.sql")


def dump():
    conn = sqlite3.connect(DB_PATH)
    DUMP.parent.mkdir(parents=True, exist_ok=True)
    tmp = DUMP.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for line in conn.iterdump():          # tables first, then rows in insertion order
            f.write(line + "\n")
    tmp.replace(DUMP)
    print(f"saved {DUMP} ({DUMP.stat().st_size // 1024} KB)")


def restore():
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        print(f"{DB_PATH} already exists; leaving it as is")
        return
    if not DUMP.exists():
        print("no saved database found: starting empty (a first run will take hours)")
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DUMP.read_text(encoding="utf-8"))
    conn.commit()
    n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("games", "player_games", "soccer_matches", "soccer_player_games", "us_games", "us_player_games")}
    print("restored database:", n)


if __name__ == "__main__":
    {"dump": dump, "restore": restore}[sys.argv[1]]()
