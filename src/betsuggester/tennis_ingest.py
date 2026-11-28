"""Download ATP and WTA singles matches (results and the upcoming draw) from ESPN into the local database.

Usage: python -m betsuggester.tennis_ingest
Scans the scoreboard every few days (a tournament lasts at most two weeks and each scoreboard call lists the
whole tournament). Safe to re-run: matches are stored by id, finished ones are never overwritten with older data.
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from . import espn
from .db import connect

TOURS = ("atp", "wta")
START = dt.date(2025, 1, 1)
STEP = 4


def _games(competitor):
    ls = competitor.get("linescores") or []
    return [int(x.get("value", 0)) for x in ls]


def parse_competition(ev: dict, tour: str, comp: dict) -> dict | None:
    cs = comp.get("competitors") or []
    if len(cs) != 2 or any("athlete" not in c for c in cs):
        return None                                           # doubles, or a bye with no opponent yet
    c1, c2 = sorted(cs, key=lambda c: c.get("order", 0))
    st = comp["status"]["type"]
    sets1, sets2 = _games(c1), _games(c2)
    done = bool(st.get("completed"))
    winner = (1 if c1.get("winner") else 2 if c2.get("winner") else 0) if done else 0
    major = int(bool(ev.get("major")))
    best_of = 5 if (major and tour == "atp") else 3
    s1 = sum(a > b for a, b in zip(sets1, sets2)); s2 = sum(b > a for a, b in zip(sets1, sets2))
    return {"match_id": comp["id"], "tour": tour, "date": comp["date"][:16], "tournament": ev["name"], "major": major, "best_of": best_of,
            "p1_id": c1["id"], "p1": c1["athlete"]["displayName"], "p1_rank": (c1.get("curatedRank") or {}).get("current"),
            "p2_id": c2["id"], "p2": c2["athlete"]["displayName"], "p2_rank": (c2.get("curatedRank") or {}).get("current"),
            "winner": winner, "sets": " ".join(f"{a}-{b}" for a, b in zip(sets1, sets2)), "status": st.get("description", ""), "state": st.get("state", ""),
            "games1": sum(sets1), "games2": sum(sets2), "sets1": s1, "sets2": s2}


def fetch_day(args):
    tour, day = args
    old = (dt.date.today() - day).days > 12
    try:
        sb = espn.get(f"tennis/{tour}/scoreboard", ttl=None if old else 900, pace=False, dates=day.strftime("%Y%m%d"))
    except Exception as e:
        print(f"  {tour} {day}: skipped ({e})")
        return []
    out = []
    for ev in sb.get("events", []):
        for gr in ev.get("groupings", []):
            name = gr["grouping"]["displayName"].lower()
            if "singles" not in name or ("women" in name) != (tour == "wta"):      # Grand Slam scoreboards list both tours
                continue
            for comp in gr["competitions"]:
                m = parse_competition(ev, tour, comp)
                if m:
                    out.append(m)
    return out


def ingest():
    conn = connect()
    last = conn.execute("SELECT MAX(date) FROM tennis_matches WHERE state='post'").fetchone()[0]
    start = START if not last else max(START, dt.date.fromisoformat(last[:10]) - dt.timedelta(days=16))
    today = dt.date.today()
    days = []
    d = start
    while d <= today + dt.timedelta(days=6):
        days.append(d); d += dt.timedelta(days=STEP)
    jobs = [(t, d) for t in TOURS for d in days]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(fetch_day, jobs))
    rows = {}
    for part in results:
        for m in part:
            rows[m["match_id"]] = m               # later scoreboard views of the same match win (more complete)
    with conn:
        conn.executemany("INSERT OR REPLACE INTO tennis_matches VALUES (:match_id,:tour,:date,:tournament,:major,:best_of,:p1_id,:p1,:p1_rank,:p2_id,:p2,:p2_rank,:winner,:sets,:status,:state,:games1,:games2,:sets1,:sets2)", list(rows.values()))
    n = conn.execute("SELECT tour, state, COUNT(*) FROM tennis_matches GROUP BY tour, state").fetchall()
    print("tennis matches:", n)


if __name__ == "__main__":
    ingest()
