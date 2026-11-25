"""Lineup adjustment for the NBA game model.

Team ratings already know a team's USUAL strength. This adds one number per team: how much more or less talent is
playing tonight than usual, where a player's talent is his recent production per game (points + 1.2 rebounds +
1.5 assists). So when a star is ruled out the team's prediction drops; when a star returns it rises.
Only two numbers are learned (how many points of margin / total one unit of talent is worth), so it cannot overfit.
"""
import numpy as np
import pandas as pd

from .db import connect

FALLBACK = 8.0      # production of a player with no history (a bench player)


def load_talent() -> pd.DataFrame:
    """Per player-game: his talent BEFORE that game (average of his previous 10 games) and whether he played."""
    pg = pd.read_sql_query("""SELECT p.game_id, p.team, p.player, p.minutes, p.pts, p.reb, p.ast, g.date FROM player_games p JOIN games g USING (game_id)
                              ORDER BY g.date, p.game_id""", connect())
    pg["date"] = pd.to_datetime(pg["date"])
    pg["comp"] = pg.pts + 1.2 * pg.reb + 1.5 * pg.ast
    pg["talent"] = pg.groupby("player")["comp"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean()).fillna(FALLBACK)
    return pg[pg.minutes > 0]


def team_talent_table(pg: pd.DataFrame) -> pd.DataFrame:
    """Total talent that actually played, per team-game, plus that team's usual (average of its previous 10 games)."""
    t = pg.groupby(["game_id", "team", "date"], as_index=False)["talent"].sum().sort_values("date")
    t["usual"] = t.groupby("team")["talent"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    t["delta"] = t["talent"] - t["usual"]
    return t[["game_id", "team", "talent", "usual", "delta"]]


# Learned on 959 unseen games (see nba_injury_backtest in the README): one unit of "talent playing tonight" is worth about
# 0.046 points of margin. Totals were NOT improved, so they are not adjusted.
KM = 0.046

# Chance a player does NOT play, by the status on ESPN's injury list. "Out" is a fact; the others are judgement calls
# that have not been tested against history (there is no free history of injury reports).
P_NOT_PLAYING = {"out": 1.0, "doubtful": 0.85, "questionable": 0.5, "day-to-day": 0.4}


def p_out(status: str) -> float:
    s = (status or "").lower()
    return next((v for k, v in P_NOT_PLAYING.items() if s.startswith(k)), 0.0)


def live_losses(team: str, injuries: dict, norm, pg: pd.DataFrame | None = None):
    """Talent a team is expected to be missing tonight.
    injuries: {normalised player name: {"status": ...}} from ESPN. Returns (total talent lost, [(name, status, talent lost)])."""
    pg = load_talent() if pg is None else pg
    pg = pg.sort_values(["date", "game_id"]).copy()
    pg["talent_now"] = pg.groupby("player")["comp"].transform(lambda s: s.rolling(10, min_periods=3).mean()).fillna(FALLBACK)
    tg = pg[pg.team == team]
    recent = list(dict.fromkeys(tg.game_id))[-10:]                       # the team's last 10 games
    rows = tg[tg.game_id.isin(recent)]
    out, total = [], 0.0
    for player, grp in rows.groupby("player"):
        status = (injuries.get(norm(player)) or {}).get("status")
        po = p_out(status)
        if po <= 0:
            continue
        lost = float(grp.talent_now.iloc[-1] * len(grp) / max(len(recent), 1) * po)   # talent x how often he normally plays x chance he sits
        total += lost; out.append((player, status, lost))
    return total, sorted(out, key=lambda x: -x[2])
