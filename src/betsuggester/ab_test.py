"""Does a feature earn its place? Compare feature sets on exactly the same unseen games.

Usage: python -m betsuggester.ab_test
Prints, per stat and test window, the log-loss change vs the current model and how many standard
errors away from zero that change is (|z| < 2 means: could just be luck).
"""
import numpy as np

from .backtest import prepare, run
from .features import FEATURES
from .model import STATS

CURRENT = list(FEATURES)
VARIANTS = {
    "A. current model": CURRENT,
    "B. drop opponent-strength": [f for f in CURRENT if f != "opp_allowed15"],
    "C. add defence-vs-position": CURRENT + ["pos_code", "opp_pos_allowed15"],
    "D. defence-vs-position instead of team": [f for f in CURRENT if f != "opp_allowed15"] + ["pos_code", "opp_pos_allowed15"],
}
SPLITS = {"2nd half of last season (14k games)": "2026-02-01", "this season (3 weeks)": "2026-11-01"}


def main():
    for stat in STATS:
        df = prepare(stat)
        for label, split in SPLITS.items():
            res = {name: run(split, stat, feats, df, quiet=True) for name, feats in VARIANTS.items()}
            base = res["A. current model"]
            print(f"\n== {stat} | {label} | {base['n_test']} test rows ==")
            for name, r in res.items():
                d = base["row_loss"] - r["row_loss"]           # positive = better than current
                z = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if name[0] != "A" else 0.0
                print(f"  {name:42s} log-loss {r['logloss']:.4f}  MAE {r['mae']:.3f}   vs A: {-d.mean():+.4f}  (z={z:+.1f})")


if __name__ == "__main__":
    main()
