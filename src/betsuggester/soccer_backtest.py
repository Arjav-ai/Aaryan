"""Walk-forward test of the match model: refit every 2 weeks using only matches played before, then
predict the next 2 weeks. Compared with a baseline that only knows the league's overall home/draw/away rates.

Usage: python -m betsuggester.soccer_backtest [start_date]
"""
import sys

import numpy as np
import pandas as pd

from .soccer_model import TeamModel, load_matches, outcome_probs, total_prob, handicap_prob

EPS = 1e-4


def walk_forward(m, start, step=14, **kw):
    start = pd.Timestamp(start); end = m.date.max() + pd.Timedelta(days=1)
    recs, t = [], start
    while t < end:
        train, test = m[m.date < t], m[(m.date >= t) & (m.date < t + pd.Timedelta(days=step))]
        t += pd.Timedelta(days=step)
        if test.empty:
            continue
        tm = TeamModel(**kw).fit(train, asof=test.date.min())
        base = {"home": (train.home_goals > train.away_goals).mean(), "draw": (train.home_goals == train.away_goals).mean(),
                "away": (train.home_goals < train.away_goals).mean()}
        for r in test.itertuples(index=False):
            M = tm.score_matrix(r.home_id, r.away_id); o = outcome_probs(M)
            lh, la = tm.expected_goals(r.home_id, r.away_id)
            res = "home" if r.home_goals > r.away_goals else "draw" if r.home_goals == r.away_goals else "away"
            h15, _ = handicap_prob(M, -1.5)
            recs.append({"res": res, **{f"p_{k}": v for k, v in o.items()}, **{f"b_{k}": v for k, v in base.items()},
                         "over25": total_prob(M, 2.5)[0], "o25": int(r.home_goals + r.away_goals > 2.5),
                         "h15": h15, "h15_hit": int(r.home_goals - r.away_goals - 1.5 > 0),
                         "mae_g": abs(lh - r.home_goals) + abs(la - r.away_goals), "n": 1})
    return pd.DataFrame(recs)


def summarize(d, label=""):
    ll = lambda p: -np.mean(np.log(np.clip(np.where(d.res == "home", p["home"], np.where(d.res == "draw", p["draw"], p["away"])), EPS, 1)))
    model = ll({k: d[f"p_{k}"] for k in ("home", "draw", "away")}); base = ll({k: d[f"b_{k}"] for k in ("home", "draw", "away")})
    br = lambda p: np.mean(sum((p[k] - (d.res == k)) ** 2 for k in ("home", "draw", "away")))
    print(f"{label}{len(d)} matches | 1X2 log-loss model {model:.4f} vs baseline {base:.4f} | Brier model "
          f"{br({k: d[f'p_{k}'] for k in ('home','draw','away')}):.4f} vs {br({k: d[f'b_{k}'] for k in ('home','draw','away')}):.4f} | "
          f"goal error {d.mae_g.mean()/2:.2f}/team")
    return d


def calibration(d):
    for name, p, hit in (("Home win", d.p_home, d.res == "home"), ("Over 2.5 goals", d.over25, d.o25 == 1), ("Home -1.5", d.h15, d.h15_hit == 1)):
        b = pd.cut(p, [0, .2, .3, .4, .5, .6, .7, 1.0])
        print(f"\n{name}: said vs actual"); print(pd.DataFrame({"p": p, "hit": hit.astype(int), "b": b}).groupby("b", observed=True).agg(n=("hit", "size"), said=("p", "mean"), actual=("hit", "mean")).round(3).to_string())


if __name__ == "__main__":
    m = load_matches()
    d = walk_forward(m, sys.argv[1] if len(sys.argv) > 1 else "2026-02-01")
    summarize(d); calibration(d)
