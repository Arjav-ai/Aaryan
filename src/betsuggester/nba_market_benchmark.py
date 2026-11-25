"""How does our NBA game model compare with the bookmaker (DraftKings pre-game lines) on the same unseen games?

Usage: python -m betsuggester.nba_market_benchmark [start_date]
Prints: typical error of each, whether the model adds anything the line lacks, and a pretend-betting result.
"""
import sys

import numpy as np
import pandas as pd

from . import nba_game_model as M
from .db import connect
from .nba_game_backtest import ll, walk_forward


def american_to_prob(ml):
    ml = np.asarray(ml, dtype=float)
    return np.where(ml > 0, 100 / (ml + 100), -ml / (-ml + 100))


def load(start="2026-01-01"):
    g = M.add_rest(M.load_games())
    d = walk_forward(g, start)
    lines = pd.read_sql_query("SELECT game_id, spread, total AS line_total, home_ml, away_ml FROM nba_lines", connect())
    d = d.merge(lines, on="game_id").dropna(subset=["spread", "line_total", "home_ml", "away_ml"])
    d["mkt_m"] = -d.spread                                  # bookmaker's expected home margin
    ph, pa = american_to_prob(d.home_ml), american_to_prob(d.away_ml)
    d["mkt_p"] = ph / (ph + pa)                             # moneyline with the bookmaker's cut removed
    return d


def report(d):
    n = len(d); win = (d.margin > 0).astype(float)
    print(f"{n} regular-season games with both our prediction and the bookmaker's line\n")
    print("Typical miss (mean absolute error, points):")
    print(f"  margin  : our model {np.mean(np.abs(d.margin - d.mu_m)):.2f} | bookmaker {np.mean(np.abs(d.margin - d.mkt_m)):.2f} | flat guess {np.mean(np.abs(d.margin - d.base_m)):.2f}")
    print(f"  total   : our model {np.mean(np.abs(d.total - d.mu_t)):.2f} | bookmaker {np.mean(np.abs(d.total - d.line_total)):.2f} | flat guess {np.mean(np.abs(d.total - d.base_t)):.2f}")
    print(f"  spread of the miss (std): model {np.std(d.margin - d.mu_m):.2f} | bookmaker {np.std(d.margin - d.mkt_m):.2f}")
    p_ours = np.array([M.moneyline(m)["home"] for m in d.mu_m])
    print(f"\nWho wins (log-loss, lower is better): our model {ll(p_ours, win):.4f} | bookmaker {ll(d.mkt_p.to_numpy(), win):.4f} | flat guess {ll(d.base_win.to_numpy(), win):.4f}")
    print(f"  picks the winner: our model {((p_ours > .5) == (win == 1)).mean():.1%} | bookmaker {((d.mkt_p > .5) == (win == 1)).mean():.1%}")
    # does our model know anything the line does not?  margin = a + b*line + c*model
    X = np.column_stack([np.ones(n), d.mkt_m, d.mu_m]); beta = np.linalg.lstsq(X, d.margin.to_numpy(), rcond=None)[0]
    cov = np.linalg.inv(X.T @ X) * np.var(d.margin.to_numpy() - X @ beta); se = np.sqrt(np.diag(cov))
    print(f"\nDoes the model add anything beyond the line?  margin ~ {beta[1]:.2f} x line + {beta[2]:+.2f} x model   (model weight {beta[2]:+.2f} +/- {1.96 * se[2]:.2f})")
    for k in (0, .25, .5):
        blend = d.mkt_m + k * (d.mu_m - d.mkt_m)
        print(f"  line moved {int(k * 100):2d}% of the way toward our model: typical miss {np.mean(np.abs(d.margin - blend)):.2f}")
    # pretend betting: flat 1 unit at -110 whenever the model disagrees with the line by enough
    print("\nPretend betting on the spread at -110 (bet the side our model prefers when its edge is at least X):")
    pc = np.array([M.spread(mu, -sp, "home")[0] for mu, sp in zip(d.mu_m, d.spread)])   # our P(home covers) at the market line
    res = d.margin + d.spread                               # >0 home covers
    for thr in (0.0, 0.03, 0.06, 0.10):
        side_home = pc > .5; edge = np.abs(pc - .5); sel = edge >= thr
        wins = np.where(side_home, res > 0, res < 0)[sel]; pushes = (res == 0)[sel]
        pnl = np.where(pushes, 0, np.where(wins, 100 / 110, -1.0)); nb = sel.sum()
        print(f"  edge >= {thr:4.0%}: {nb:4d} bets, won {wins[~pushes].mean() if nb else float('nan'):.1%} (need 52.4% to break even), profit {pnl.sum():+.1f} units ({pnl.mean() * 100:+.1f}% per bet)")


if __name__ == "__main__":
    report(load(sys.argv[1] if len(sys.argv) > 1 else "2026-01-01"))
