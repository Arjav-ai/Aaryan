"""Walk-forward test of the NBA game model on games it has never seen (refit every 2 weeks).

Usage: python -m betsuggester.nba_game_backtest [start_date]
"""
import sys

import numpy as np
import pandas as pd

from . import nba_game_model as M


def walk_forward(g, start, step=14, **kw):
    start = pd.Timestamp(start); end = g.date.max() + pd.Timedelta(days=1)
    out, t = [], start
    while t < end:
        train, test = g[g.date < t], g[(g.date >= t) & (g.date < t + pd.Timedelta(days=step))]
        t += pd.Timedelta(days=step)
        if test.empty:
            continue
        gm = M.GameModel(**kw).fit(train, asof=test.date.min())
        base_m, base_t = train.home_pts.sub(train.away_pts).mean(), train.home_pts.add(train.away_pts).mean()
        base_win = (train.home_pts > train.away_pts).mean()
        for r in test.itertuples(index=False):
            mh, ma = gm.expected_points(r.home, r.away, r.home_b2b, r.away_b2b)
            out.append({"date": r.date, "mu_m": mh - ma, "mu_t": mh + ma, "margin": r.home_pts - r.away_pts, "total": r.home_pts + r.away_pts,
                        "base_m": base_m, "base_t": base_t, "base_win": base_win})
    return pd.DataFrame(out)


def ll(p, hit, eps=1e-4):
    p = np.clip(p, eps, 1 - eps); return -np.mean(hit * np.log(p) + (1 - hit) * np.log(1 - p))


def evaluate(d, sd_m=M.SD_MARGIN, sd_t=M.SD_TOTAL, quiet=False):
    win = (d.margin > 0).astype(float)
    p_ml = np.array([M.moneyline(m, sd_m)["home"] for m in d.mu_m])
    res = {"ml": ll(p_ml, win), "ml_base": ll(d.base_win.to_numpy(), win), "ml_acc": float(((p_ml > .5) == (win == 1)).mean())}
    sp, spb, to, tob = [], [], [], []
    for off in (-9, -6, -3, 0, 3, 6, 9):            # spread lines around the model's own number
        L = -(np.floor(d.mu_m.to_numpy()) + .5) + off   # home handicap
        hit = np.array([(m + l > 0) for m, l in zip(d.margin, L)], float)
        p = np.array([M.spread(mu, l, "home", sd_m)[0] for mu, l in zip(d.mu_m, L)])
        pb = np.array([M.spread(b, l, "home", sd_m)[0] for b, l in zip(d.base_m, L)])
        sp.append(ll(p, hit)); spb.append(ll(pb, hit))
    for off in (-12, -8, -4, 0, 4, 8, 12):
        L = np.floor(d.mu_t.to_numpy()) + .5 + off
        hit = (d.total.to_numpy() > L).astype(float)
        p = np.array([M.total(mu, l, "over", sd_t)[0] for mu, l in zip(d.mu_t, L)])
        pb = np.array([M.total(b, l, "over", sd_t)[0] for b, l in zip(d.base_t, L)])
        to.append(ll(p, hit)); tob.append(ll(pb, hit))
    res.update(spread=np.mean(sp), spread_base=np.mean(spb), total=np.mean(to), total_base=np.mean(tob),
               mae_m=float(np.mean(np.abs(d.mu_m - d.margin))), mae_m_base=float(np.mean(np.abs(d.base_m - d.margin))),
               mae_t=float(np.mean(np.abs(d.mu_t - d.total))), mae_t_base=float(np.mean(np.abs(d.base_t - d.total))),
               sd_m_resid=float((d.margin - d.mu_m).std()), sd_t_resid=float((d.total - d.mu_t).std()))
    if not quiet:
        print(f"{len(d)} games | moneyline log-loss {res['ml']:.4f} (flat guess {res['ml_base']:.4f}), picks the winner {res['ml_acc']:.1%}")
        print(f"spread log-loss {res['spread']:.4f} (flat {res['spread_base']:.4f}) | total log-loss {res['total']:.4f} (flat {res['total_base']:.4f})")
        print(f"margin error {res['mae_m']:.2f} pts (flat {res['mae_m_base']:.2f}) | total error {res['mae_t']:.2f} (flat {res['mae_t_base']:.2f}) | residual sd margin {res['sd_m_resid']:.2f}, total {res['sd_t_resid']:.2f}")
    return res


def calibration(d, sd_m=M.SD_MARGIN, sd_t=M.SD_TOTAL):
    rows = []
    for off in (-9, -6, -3, 0, 3, 6, 9):
        L = -(np.floor(d.mu_m.to_numpy()) + .5) + off
        rows.append(pd.DataFrame({"kind": "spread (home covers)", "p": [M.spread(mu, l, "home", sd_m)[0] for mu, l in zip(d.mu_m, L)], "hit": [(m + l > 0) for m, l in zip(d.margin, L)]}))
    for off in (-12, -8, -4, 0, 4, 8, 12):
        L = np.floor(d.mu_t.to_numpy()) + .5 + off
        rows.append(pd.DataFrame({"kind": "total (over)", "p": [M.total(mu, l, "over", sd_t)[0] for mu, l in zip(d.mu_t, L)], "hit": d.total.to_numpy() > L}))
    rows.append(pd.DataFrame({"kind": "moneyline (home wins)", "p": [M.moneyline(m, sd_m)["home"] for m in d.mu_m], "hit": d.margin > 0}))
    r = pd.concat(rows); r["hit"] = r.hit.astype(int); r["b"] = pd.cut(r.p, [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1])
    for k, g in r.groupby("kind"):
        print(f"\n{k}: said vs actual"); print(g.groupby("b", observed=True).agg(n=("hit", "size"), said=("p", "mean"), actual=("hit", "mean")).round(3).to_string())


if __name__ == "__main__":
    g = M.add_rest(M.load_games())
    d = walk_forward(g, sys.argv[1] if len(sys.argv) > 1 else "2026-01-01")
    evaluate(d); calibration(d)
