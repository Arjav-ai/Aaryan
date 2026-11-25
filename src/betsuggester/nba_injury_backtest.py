"""Does knowing tonight's lineup improve the NBA game model? (walk-forward on unseen games, lineups known)

The team ratings capture a team's USUAL strength. This adds KM points of margin per unit of 'talent playing tonight vs
usual' (talent = points + 1.2 rebounds + 1.5 assists per game, last 10 games). KM is re-learned before every 2-week fold.

Usage: python -m betsuggester.nba_injury_backtest
Result recorded in the README: typical margin miss 11.65 -> 11.54 points (bookmaker 10.93).
"""
import numpy as np
import pandas as pd

from . import nba_game_model as M
from . import nba_injury_adjust as A
from .db import connect


def run(min_minutes=0, start="2026-01-01"):
    g0 = M.add_rest(M.load_games())
    lines = pd.read_sql_query("SELECT game_id, spread FROM nba_lines", connect())
    pg = A.load_talent().sort_values(["date", "game_id"])
    pg["pre_min"] = pg.groupby("player")["minutes"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean()).fillna(10.0)
    p = pg[pg.pre_min >= min_minutes]
    t = p.groupby(["game_id", "team", "date"], as_index=False)["talent"].sum().sort_values("date")
    t["delta"] = t["talent"] - t.groupby("team")["talent"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    g = g0.merge(t[["game_id", "team", "delta"]].rename(columns={"team": "home", "delta": "dh"}), on=["game_id", "home"], how="left") \
          .merge(t[["game_id", "team", "delta"]].rename(columns={"team": "away", "delta": "da"}), on=["game_id", "away"], how="left")
    out, cut, end = [], pd.Timestamp(start), g.date.max() + pd.Timedelta(days=1)
    while cut < end:
        te = g[(g.date >= cut) & (g.date < cut + pd.Timedelta(days=14))]; tr = g[g.date < cut].dropna(subset=["dh", "da"]); cut += pd.Timedelta(days=14)
        if te.empty:
            continue
        tm = M.GameModel().fit(g[g.date < te.date.min()], asof=te.date.min())
        base = np.array([a - b for a, b in (tm.expected_points(r.home, r.away, r.home_b2b, r.away_b2b) for r in tr.itertuples())])
        x = (tr.dh - tr.da).to_numpy(); km = (x @ ((tr.home_pts - tr.away_pts).to_numpy() - base)) / (x @ x)
        for r in te.itertuples():
            mh, ma = tm.expected_points(r.home, r.away, r.home_b2b, r.away_b2b)
            dh = 0 if np.isnan(r.dh) else r.dh; da = 0 if np.isnan(r.da) else r.da
            out.append({"game_id": r.game_id, "margin": r.home_pts - r.away_pts, "base": mh - ma, "adj": mh - ma + km * (dh - da), "k": km})
    d = pd.DataFrame(out).merge(lines, on="game_id"); d["mkt"] = -d.spread
    return d


if __name__ == "__main__":
    d = run()
    print(f"{len(d)} unseen games with the bookmaker's line. Typical margin miss (points):")
    print(f"  team ratings only {np.mean(np.abs(d.margin - d.base)):.2f} | + tonight's lineup {np.mean(np.abs(d.margin - d.adj)):.2f} | bookmaker {np.mean(np.abs(d.margin - d.mkt)):.2f}")
    print(f"  points of margin per unit of talent: {d.k.mean():.3f}   (KM in nba_injury_adjust.py)")
