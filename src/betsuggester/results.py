"""Write data/results.json: final scores and player stats for games of the last 21 days, so the page can settle the bets
you track. NBA games are keyed by "date|home team code", football matches by ESPN match id.

Usage: python -m betsuggester.results
"""
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from .db import connect

OUT = Path("data/results.json")
DAYS = 21


def build(days: int = DAYS) -> dict:
    conn = connect()
    since = (pd.Timestamp.today().normalize() - pd.Timedelta(days=days)).date().isoformat()
    nba = []
    games = pd.read_sql_query("""SELECT g.game_id, g.date, g.home_pts, g.away_pts, hp.team AS home, ap.team AS away FROM games g
        JOIN (SELECT DISTINCT game_id, team FROM player_games WHERE is_home = 1) hp USING (game_id)
        JOIN (SELECT DISTINCT game_id, team FROM player_games WHERE is_home = 0) ap USING (game_id) WHERE g.date >= ?""", conn, params=(since,))
    pl = pd.read_sql_query("SELECT p.game_id, p.player, p.pts, p.reb, p.ast, p.fg3 FROM player_games p JOIN games g USING (game_id) WHERE g.date >= ?", conn, params=(since,))
    by_game = {k: g for k, g in pl.groupby("game_id")}
    for r in games.itertuples(index=False):
        p = by_game.get(r.game_id)
        nba.append({"key": f"{r.date}|{r.home}", "home": r.home, "away": r.away, "home_pts": int(r.home_pts), "away_pts": int(r.away_pts),
                    "players": {x.player: [int(x.pts), int(x.reb), int(x.ast), int(x.fg3)] for x in p.itertuples()} if p is not None else {}})
    fb = []
    ms = pd.read_sql_query("SELECT match_id, date, home, away, home_goals, away_goals FROM soccer_matches WHERE date >= ?", conn, params=(since,))
    fp = pd.read_sql_query("SELECT match_id, player, shots, sot, goals, assists FROM soccer_player_games WHERE date >= ?", conn, params=(since,))
    fby = {k: g for k, g in fp.groupby("match_id")}
    for r in ms.itertuples(index=False):
        p = fby.get(r.match_id)
        fb.append({"key": str(r.match_id), "home": r.home, "away": r.away, "home_goals": int(r.home_goals), "away_goals": int(r.away_goals),
                   "players": {x.player: [int(x.shots), int(x.sot), int(x.goals), int(x.assists)] for x in p.itertuples()} if p is not None else {}})
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "days": days,
            "nba_stats": ["pts", "reb", "ast", "fg3"], "football_stats": ["shots", "sot", "goals", "assists"], "nba": nba, "football": fb}


def main():
    d = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, separators=(",", ":")))
    print(f"wrote {OUT}: {len(d['nba'])} NBA games, {len(d['football'])} football matches, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
