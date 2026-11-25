"""Download the bookmaker's pre-game NBA lines (spread, total, moneyline) from ESPN for every game in the database.
Used ONLY to measure how our model compares with the market, never as an input.

Usage: python -m betsuggester.nba_lines
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import espn
from .db import connect
from .predict import ESPN_TO_BBR


def fetch_one(espn_id):
    try:
        s = espn.get("basketball/nba/summary", pace=False, event=espn_id)
    except Exception:          # a game page that does not exist (or a hiccup): skip it, we only need most games
        return None
    pc = s.get("pickcenter") or []
    for p in pc:                                           # first provider that has a full set of numbers
        if p.get("spread") is not None and p.get("overUnder") is not None:
            return {"provider": p["provider"]["name"], "spread": float(p["spread"]), "total": float(p["overUnder"]),
                    "home_ml": (p.get("homeTeamOdds") or {}).get("moneyLine"), "away_ml": (p.get("awayTeamOdds") or {}).get("moneyLine")}
    return None


def main():
    conn = connect()
    have = {r[0] for r in conn.execute("SELECT game_id FROM nba_lines")}
    games = pd.read_sql_query("""SELECT g.game_id, g.date, hp.team home FROM games g
        JOIN (SELECT DISTINCT game_id, team FROM player_games WHERE is_home = 1) hp USING (game_id)""", conn)
    todo = games[~games.game_id.isin(have)]
    print(f"{len(games)} games, {len(todo)} still to look up")
    # 1) ESPN event ids by date (one scoreboard per game day)
    ids = {}
    for date in sorted(todo.date.unique()):
        sb = espn.get("basketball/nba/scoreboard", ttl=None if date < str(pd.Timestamp.today().date()) else 3600, dates=date.replace("-", ""))
        for ev in sb.get("events", []):
            h = [c for c in ev["competitions"][0]["competitors"] if c["homeAway"] == "home"][0]["team"]["abbreviation"]
            ids[(date, ESPN_TO_BBR.get(h, h))] = ev["id"]
    # BBR dates are local (US) dates; ESPN lists by US date too, so (date, home team) identifies the game
    pairs = [(r.game_id, ids.get((r.date, r.home))) for r in todo.itertuples()]
    pairs = [(g, e) for g, e in pairs if e]
    print(f"matched {len(pairs)} of {len(todo)} games to ESPN events")
    with ThreadPoolExecutor(8) as pool:
        lines = list(pool.map(lambda p: fetch_one(p[1]), pairs))
    n = 0
    with conn:
        for (gid, eid), ln in zip(pairs, lines):
            if ln:
                conn.execute("INSERT OR REPLACE INTO nba_lines VALUES (?,?,?,?,?,?,?)", (gid, eid, ln["provider"], ln["spread"], ln["total"], ln["home_ml"], ln["away_ml"])); n += 1
    print(f"saved lines for {n} games")


if __name__ == "__main__":
    main()
