"""Walk-forward tests for the American football models (each prediction uses only data from before that day).

Usage: python -m betsuggester.us_backtest games|props [nfl|cfb]
"""
import sys

import numpy as np
import pandas as pd
from scipy import stats

from . import us_model as M


def games_test(league, ridge=5.0, half_life=120, start_week=5, verbose=True):
    g, _ = M.load(league)
    season = g.season.max()
    test = g[(g.season == season) & (g.week >= start_week)]
    rows = []
    for (date,), day in test.groupby([test.date.dt.normalize()]):
        train = g[g.date < date]
        gm = M.fit_games(train, date, ridge, half_life)
        for r in day.itertuples(index=False):
            if r.home_id not in gm.idx or r.away_id not in gm.idx:
                continue
            mh, ma = gm.expected_points(r.home_id, r.away_id)
            rows.append((r.home_pts - r.away_pts, mh - ma, r.home_pts + r.away_pts, mh + ma, r.spread, r.total))
    a = pd.DataFrame(rows, columns=["margin", "mu_margin", "total", "mu_total", "spread", "mkt_total"])
    out = {"n": len(a), "margin_rmse": float(np.sqrt(((a.margin - a.mu_margin) ** 2).mean())), "total_rmse": float(np.sqrt(((a.total - a.mu_total) ** 2).mean())),
           "winner": float((np.sign(a.margin) == np.sign(a.mu_margin)).mean()), "naive_margin_rmse": float(np.sqrt(((a.margin - a.margin.mean()) ** 2).mean()))}
    m = a.dropna(subset=["spread"])
    if len(m) > 20:
        out["n_mkt"] = len(m)
        out["mkt_margin_rmse"] = float(np.sqrt(((m.margin + m.spread) ** 2).mean()))
        out["model_margin_rmse_same"] = float(np.sqrt(((m.margin - m.mu_margin) ** 2).mean()))
        out["mkt_winner"] = float((np.sign(m.margin) == np.sign(-m.spread)).mean())
        out["model_winner_same"] = float((np.sign(m.margin) == np.sign(m.mu_margin)).mean())
        mt = a.dropna(subset=["mkt_total"])
        out["mkt_total_rmse"] = float(np.sqrt(((mt.total - mt.mkt_total) ** 2).mean()))
        out["model_total_rmse_same"] = float(np.sqrt(((mt.total - mt.mu_total) ** 2).mean()))
    if verbose:
        print(league, {k: round(v, 3) if isinstance(v, float) else v for k, v in out.items()})
    return out, a


def props_pairs(league, start_date=None, **kw):
    """(stat, mu, n, y, player) for every player-game that qualifies, predicted only from earlier games."""
    g, p = M.load(league)
    pj = M.Projector(g, p, league=league, **kw)
    start = pd.Timestamp(start_date) if start_date else g.date.min() + pd.Timedelta(days=60)
    meta = g.set_index("game_id")
    rows = []
    for r in p[p.date >= start].itertuples(index=False):
        gm = meta.loc[r.game_id]
        opp = gm.away_id if r.team_id == gm.home_id else gm.home_id
        for stat, (rc, thr) in pj.role.items():
            if getattr(r, rc) < thr:      # only evaluate games where he actually had the role (those are the props a page would offer)
                continue
            res = pj.project(r.player_id, stat, r.team_id, opp, r.date)
            if res:
                rows.append((stat, res[0], res[1], getattr(r, stat), r.player_id, r.date))
    d = pd.DataFrame(rows, columns=["stat", "mu", "n", "y", "player", "date"])
    d["y"] = d["y"].clip(lower=0)        # a few quarterbacks lose yards on the ground; the count model starts at zero
    return d


def fit_alpha(d):
    best = None
    for a in np.exp(np.linspace(np.log(0.02), np.log(2.0), 40)):
        ll = M.nb_loglik(d.y.to_numpy(), d.mu.to_numpy(), a).sum()
        if best is None or ll > best[1]:
            best = (a, ll)
    return best[0]


def calibration(d, alpha):
    """Predicted chance of 'over' at the line nearest the model's own number vs how often it happened."""
    line = np.floor(d.mu) + 0.5
    pr = np.array([M.nb_pmf_over(m, alpha, l) for m, l in zip(d.mu, line)])
    hit = (d.y.to_numpy() > line)
    bins = [0, .3, .4, .5, .6, .7, 1.01]
    out = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        k = (pr >= lo) & (pr < hi)
        if k.sum() >= 15:
            out.append((f"{lo:.0%}-{min(hi,1):.0%}", int(k.sum()), round(float(pr[k].mean()), 3), round(float(hit[k].mean()), 3)))
    return out


def props_test(league, **kw):
    d = props_pairs(league, **kw)
    print(league, "pairs:", len(d))
    alphas = {}
    for stat in M.STAT_ORDER:
        s = d[d.stat == stat]
        a = max(fit_alpha(s), 0.05); alphas[stat] = round(float(a), 3)
        ll = M.nb_loglik(s.y.to_numpy(), s.mu.to_numpy(), a).mean()
        flat = M.nb_loglik(s.y.to_numpy(), np.full(len(s), s.y.mean()), fit_alpha(s.assign(mu=s.y.mean()))).mean()
        print(f"  {stat:9s} n={len(s):5d} alpha={a:.3f} loglik={ll:.3f} (everyone-gets-the-average: {flat:.3f}) mean mu {s.mu.mean():.2f} vs actual {s.y.mean():.2f}")
        print("     calibration (predicted -> happened):", calibration(s, a))
    print("  alphas:", alphas)
    return d, alphas


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "games"
    for lg in (sys.argv[2:] or ["nfl", "cfb"]):
        if what == "games":
            for ridge in (2, 5, 10, 20):
                print("ridge", ridge, end=" "); games_test(lg, ridge=ridge)
        else:
            props_test(lg)
