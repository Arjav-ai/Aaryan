"""Safety checks on the refreshed data before anything is published.

Exit code 0 = safe to publish. Prints one line per sport. Usage: python -m betsuggester.check_outputs
"""
import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path

from .db import DB_PATH

MIN_ROWS = {"games": 1580, "player_games": 34000, "soccer_matches": 2500, "soccer_player_games": 79000}   # floors: today's counts
MAX_AGE_HOURS = 3


def age_hours(d):
    return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(d["generated_at"] + ("+00:00" if "+" not in d["generated_at"] else ""))).total_seconds() / 3600


def check_players(d, min_players, problems):
    if len(d["players"]) < min_players:
        problems.append(f"only {len(d['players'])} players")
    for p in d["players"]:
        for s, v in p["stats"].items():
            if not all(math.isfinite(x) for x in (v["mu"], v["alpha"], v["avg10"])) or v["mu"] < 0 or not 0 < v["alpha"] <= 1:
                problems.append(f"bad numbers for {p['name']} {s}"); return


def main() -> int:
    bad = False
    conn = sqlite3.connect(DB_PATH)
    for t, floor in MIN_ROWS.items():
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        if n < floor:
            print(f"DATABASE PROBLEM: {t} has {n} rows (expected at least {floor})"); bad = True
    for name, path, min_players in (("NBA", "data/predictions.json", 50), ("Football", "data/predictions_soccer.json", 200)):
        problems = []
        try:
            d = json.loads(Path(path).read_text())
            age = age_hours(d)
            if d["games"]:
                check_players(d, min_players, problems)
            else:
                print(f"  note: {name} has no upcoming games right now (break / off-season): that is fine")
            if name == "NBA":
                for g in d["games"]:
                    n = g.get("nba")
                    if not n or not all(math.isfinite(n[k]) for k in ("mu_home", "mu_away", "mu_margin", "mu_total")) or not (170 < n["mu_total"] < 270) or abs(n["mu_margin"]) > 30:
                        problems.append(f"bad game numbers for {g['away']} at {g['home']}"); break
            if name == "Football":
                for g in d["games"]:
                    if not 0.999 < sum(map(sum, g["grid"])) < 1.001:
                        problems.append(f"scoreline grid does not add to 100% for {g['home']} v {g['away']}"); break
                for lg, o in d["outrights"].items():
                    for m in o["markets"]:
                        tot = sum(t[m["key"]] for t in o["teams"])
                        if not any(abs(tot - k) < 0.1 for k in (1, 4, 2, 3, 8, 16, 12)):
                            problems.append(f"{o['name']} {m['label']} adds to {tot:.2f}")
            status = "FRESH" if age <= MAX_AGE_HOURS else f"STALE ({age:.0f}h old: refresh did not produce new predictions)"
        except Exception as e:
            problems.append(f"unreadable: {e}"); status = "INVALID"
        if problems:
            status = "INVALID"; bad = True
        print(f"{name}: {status}" + (f" | {'; '.join(problems)}" if problems else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
