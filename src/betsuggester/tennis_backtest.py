"""Walk-forward tests for the tennis model.  Usage: python -m betsuggester.tennis_backtest"""
import numpy as np
import pandas as pd
from scipy import stats

from . import tennis_model as T


def elo_test(tour, scale=None, verbose=True):
    if scale:
        T.SCALE[tour] = scale
    df = T.load(tour)
    wf, elo = T.walk_forward(df, tour)
    test = wf[wf.date >= "2026-01-01"]
    test = test[test.min_n >= 5]       # both players already have 5+ matches in the data
    p, y = test.p.clip(0.001, 0.999), test.y
    ll = -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
    out = {"n": len(test), "logloss": float(ll), "coin": 0.6931, "accuracy": float(((test.p > .5) == (y == 1)).mean())}
    if verbose:
        print(tour, {k: round(v, 4) if isinstance(v, float) else v for k, v in out.items()})
    return out, test, df


def calibration(test):
    bins = [0, .3, .4, .5, .6, .7, .8, 1.01]
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        k = (test.p >= lo) & (test.p < hi)
        if k.sum() >= 20:
            rows.append((f"{lo:.0%}-{min(hi,1):.0%}", int(k.sum()), round(float(test.p[k].mean()), 3), round(float(test.y[k].mean()), 3)))
    return rows


def games_test(tour, h0, test, df):
    d = df.set_index("match_id")
    rows = []
    for r in test.itertuples(index=False):
        m = d.loc[r.match_id]
        if m.status != "Final":
            continue
        bo = 5 if max(m.sets1, m.sets2) >= 3 else 3
        pw, mt, st, mm, sm = T.for_win_prob(round(float(r.p) * 50) / 50, h0, bo)
        rows.append((m.games1 + m.games2, mt, st, m.games1 - m.games2, mm, sm, bo))
    a = pd.DataFrame(rows, columns=["total", "mu_t", "sd_t", "margin", "mu_m", "sd_m", "bo"])
    return a


def main():
    for tour in ("atp", "wta"):
        print("=== ", tour)
        best = None
        for sc in (0.0025, 0.0030, 0.0035, 0.0040, 0.0050):
            o, _, _ = elo_test(tour, sc, verbose=False)
            print(f"  scale {sc}: logloss {o['logloss']:.4f} accuracy {o['accuracy']:.3f}")
            if best is None or o["logloss"] < best[1]:
                best = (sc, o["logloss"])
        T.SCALE[tour] = best[0]
        o, test, df = elo_test(tour)
        print("  calibration (predicted -> happened):", calibration(test))
        # the totals model: pick the hold rate that fits best
        res = []
        for h0 in ([0.76, 0.78, 0.80, 0.82, 0.84] if tour == "atp" else [0.58, 0.61, 0.64, 0.67, 0.70]):
            a = games_test(tour, h0, test.sample(min(len(test), 1500), random_state=1), df)
            res.append((h0, float(((a.total - a.mu_t) ** 2).mean() ** 0.5), float((a.total - a.mu_t).mean())))
            print(f"  hold {h0}: total games RMSE {res[-1][1]:.2f}, bias {res[-1][2]:+.2f}")
        h0 = min(res, key=lambda x: x[1])[0]
        a = games_test(tour, h0, test, df)
        print(f"  chosen hold {h0}: n={len(a)}, total games: model sd {a.sd_t.mean():.2f} vs actual miss sd {(a.total - a.mu_t).std():.2f}; margin sd {a.sd_m.mean():.2f} vs {(a.margin - a.mu_m).std():.2f}")
        a3 = a[a.bo == 3]
        line = np.floor(a3.mu_t) + 0.5
        pr = 1 - stats.norm.cdf((line - a3.mu_t) / a3.sd_t)
        hit = (a3.total > line)
        for lo, hi in [(0, .4), (.4, .5), (.5, .6), (.6, 1.01)]:
            k = (pr >= lo) & (pr < hi)
            if k.sum() >= 30:
                print(f"    total over: predicted {pr[k].mean():.3f} happened {hit[k].mean():.3f} (n={int(k.sum())})")
        print(f"  best-of-5 matches in test: {int((a.bo == 5).sum())}")


if __name__ == "__main__":
    main()
