"""Honest test: train on the past, predict games the model has never seen.

Usage: python -m betsuggester.backtest [split_date]   (tests points, rebounds, assists, threes)
"""
import sys

import numpy as np
import pandas as pd

from .features import ALL_FEATURES, add_features, load_player_games
from .model import LINE_OFFSETS, STATS, fit_calibrated

EPS = 1e-4


def prepare(stat):
    """Features for every past player-game (slow: do once per stat, reuse for many tests)."""
    df = add_features(load_player_games(), stat).dropna(subset=ALL_FEATURES)
    return df[(df.games_prior >= 5) & (df.min_avg10 >= 15)]  # players who'd realistically have props


def run(split="2026-11-01", stat="pts", features=None, df=None, quiet=False):
    df = prepare(stat) if df is None else df
    train, test = df[df.date < split], df[df.date >= split]
    m = fit_calibrated(train, stat, features)
    mu, y, base = m.mean(test), test[stat].to_numpy(), test["stat_avg10"].to_numpy()

    # Typical bookmaker-style lines: the player's last-10 average rounded to a .5, a few steps either side
    losses, naive, recs = [], [], []
    for off in LINE_OFFSETS[stat]:
        line = np.floor(base + off) + 0.5
        hit = y > line
        p, pn = (np.clip(m.p_over(x, line), EPS, 1 - EPS) for x in (mu, base))
        losses.append(-(hit * np.log(p) + ~hit * np.log(1 - p)))
        naive.append(-(hit * np.log(pn) + ~hit * np.log(1 - pn)))
        recs.append(pd.DataFrame({"p": p, "hit": hit.astype(int)}))
    out = {"n_train": len(train), "n_test": len(test),
           "mae": float(np.mean(np.abs(mu - y))), "naive_mae": float(np.mean(np.abs(base - y))),
           "logloss": float(np.mean(losses)), "naive_logloss": float(np.mean(naive)),
           "row_loss": np.mean(losses, axis=0)}   # one number per test row (for paired comparisons)
    if not quiet:
        print(f"train {out['n_train']} rows, test {out['n_test']} rows (games from {split})")
        print(f"avg error (MAE): model {out['mae']:.2f}  vs simple last-10 avg {out['naive_mae']:.2f}")
        print(f"log-loss (lower is better): model {out['logloss']:.4f}  naive {out['naive_logloss']:.4f}  coin-flip 0.6931")
        r = pd.concat(recs)
        r["bucket"] = pd.cut(r.p, [0, .2, .3, .4, .5, .6, .7, .8, .9, 1.0])
        print("\nCalibration: when the model says X%, how often did it actually hit?")
        print(r.groupby("bucket", observed=True).agg(n=("hit", "size"), said=("p", "mean"), actual=("hit", "mean")).round(3).to_string())
    return out


if __name__ == "__main__":
    for st in STATS:
        print(f"\n===== {st} =====")
        run(sys.argv[1] if len(sys.argv) > 1 else "2026-11-01", st)
