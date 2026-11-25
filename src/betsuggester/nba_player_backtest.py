"""Does a player-rated game model (with lineups known) beat the team-rated one, and how close does it get to the bookmaker?
Lineups here are the players who actually played, with their PRE-game average minutes: this is the 'injuries are known'
case, i.e. the best the live system could do if the injury list were perfect.

Usage: python -m betsuggester.nba_player_backtest [start_date]
"""
import sys

import numpy as np
import pandas as pd

from . import nba_game_model as M
from . import nba_player_model as P
from .nba_market_benchmark import american_to_prob
from .db import connect
from .nba_game_backtest import ll


def run(start="2026-01-01", step=14, **kw):
    g = M.add_rest(M.load_games()); lu = P.load_lineups()
    lines = pd.read_sql_query("SELECT game_id, spread, total AS line_total, home_ml, away_ml FROM nba_lines", connect())
    out, t, end = [], pd.Timestamp(start), g.date.max() + pd.Timedelta(days=1)
    lineups = {k: list(zip(x.player, x.pre_min)) for k, x in lu.groupby(["game_id", "team"])}
    while t < end:
        train, test = g[g.date < t], g[(g.date >= t) & (g.date < t + pd.Timedelta(days=step))]
        t += pd.Timedelta(days=step)
        if test.empty:
            continue
        team = M.GameModel().fit(train, asof=test.date.min()); ply = P.PlayerGameModel(**kw).fit(train, lu, asof=test.date.min())
        for r in test.itertuples(index=False):
            h, a = lineups.get((r.game_id, r.home), []), lineups.get((r.game_id, r.away), [])
            th, ta = team.expected_points(r.home, r.away, r.home_b2b, r.away_b2b)
            ph, pa = ply.expected_points(h, a, r.home_b2b, r.away_b2b)
            out.append({"game_id": r.game_id, "date": r.date, "margin": r.home_pts - r.away_pts, "total": r.home_pts + r.away_pts,
                        "team_m": th - ta, "team_t": th + ta, "ply_m": ph - pa, "ply_t": ph + pa})
    d = pd.DataFrame(out).merge(lines, on="game_id", how="left")
    d["mkt_m"] = -d.spread; d["mkt_t"] = d.line_total
    return d


def report(d):
    m = d.dropna(subset=["mkt_m"]); n = len(m)
    print(f"{len(d)} unseen games; {n} of them also have the bookmaker's line\n")
    for label, a, b in (("margin", "margin", "m"), ("total", "total", "t")):
        row = f"typical {label} miss:"
        for name, col in (("team ratings", f"team_{b}"), ("PLAYER ratings (injuries known)", f"ply_{b}"), ("50/50 blend", None), ("bookmaker", f"mkt_{b}")):
            pred = (m[f"team_{b}"] + m[f"ply_{b}"]) / 2 if col is None else m[col]
            row += f" | {name} {np.mean(np.abs(m[a] - pred)):.2f}"
        print(row)
    for name, col in (("team ratings", "team_m"), ("player ratings", "ply_m"), ("bookmaker", "mkt_m")):
        print(f"  std of margin miss, {name}: {np.std(m.margin - m[col]):.2f}")
    X = np.column_stack([np.ones(n), m.mkt_m, ((m.team_m + m.ply_m) / 2)]); beta = np.linalg.lstsq(X, m.margin.to_numpy(), rcond=None)[0]
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X) * np.var(m.margin.to_numpy() - X @ beta)))
    print(f"\nMargin ~ {beta[1]:.2f} x bookmaker line + {beta[2]:+.2f} x our blended model   (model weight {beta[2]:+.2f} +/- {1.96 * se[2]:.2f})")


if __name__ == "__main__":
    report(run(sys.argv[1] if len(sys.argv) > 1 else "2026-01-01"))
