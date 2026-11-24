"""Honest test: train on the past, predict games the model has never seen.

Usage: python -m betsuggester.backtest [split_date]   (tests points, rebounds, assists, threes)   (default 2026-11-01)
"""
import sys

import numpy as np
import pandas as pd
from scipy import stats

from .features import FEATURES, add_features, load_player_games
from .model import LINE_OFFSETS, STATS, fit_calibrated


def run(split="2026-11-01", stat="pts"):
    df = add_features(load_player_games(), stat)
    df = df.dropna(subset=FEATURES)
    df = df[(df.games_prior >= 5) & (df.min_avg10 >= 15)]  # players who'd realistically have props
    train, test = df[df.date < split], df[df.date >= split]
    print(f"train {len(train)} rows, test {len(test)} rows (games from {split})")

    m = fit_calibrated(train, stat)
    mu = m.mean(test)
    y = test[stat].to_numpy()
    base = test["stat_avg10"].to_numpy()
    print(f"avg error (MAE): model {np.mean(np.abs(mu - y)):.2f}  vs simple last-10 avg {np.mean(np.abs(base - y)):.2f}")

    # Typical bookmaker-style lines: the player's last-10 average rounded to a .5
    rows = []
    for off in LINE_OFFSETS[stat]:
        line = np.floor(base + off) + 0.5
        rows.append(pd.DataFrame({"p": m.p_over(mu, line), "hit": (y > line).astype(int), "line_off": off}))
    r = pd.concat(rows)
    # same thing for the naive baseline (last-10 average, same spread)
    pb = pd.concat([pd.DataFrame({"p": m.p_over(base, np.floor(base + o) + 0.5)}) for o in LINE_OFFSETS[stat]])
    eps = 1e-4
    ll = lambda p, h: -np.mean(h * np.log(np.clip(p, eps, 1)) + (1 - h) * np.log(np.clip(1 - p, eps, 1)))
    print(f"log-loss (lower is better): model {ll(r.p.to_numpy(), r.hit.to_numpy()):.4f}  "
          f"naive {ll(pb.p.to_numpy(), r.hit.to_numpy()):.4f}  coin-flip 0.6931")

    print("\nCalibration: when the model says X%, how often did it actually hit?")
    r["bucket"] = pd.cut(r.p, [0, .2, .3, .4, .5, .6, .7, .8, .9, 1.0])
    out = r.groupby("bucket", observed=True).agg(n=("hit", "size"), said=("p", "mean"), actual=("hit", "mean"))
    print(out.round(3).to_string())
    return m, test


if __name__ == "__main__":
    for st in STATS:
        print(f"\n===== {st} =====")
        run(sys.argv[1] if len(sys.argv) > 1 else "2026-11-01", st)
