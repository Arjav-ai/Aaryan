"""Retro test of the outrights: pretend it is `cutoff` in last season, simulate with only the data
available then, and compare with how the season really ended.

Usage: python -m betsuggester.soccer_retro [cutoff] [sd ...]
"""
import sys

import numpy as np
import pandas as pd

from .soccer_model import TeamModel, load_matches
from .soccer_outrights import CL_BANDS, CL_NEW_SD, CL_SD, LEAGUES, domestic_bands, simulate_core, table, team_sd


def final_table(season_matches):
    t = table(season_matches); t["gd"] = t.gf - t.ga
    return t.sort_values(["points", "gd", "gf"], ascending=False).reset_index(drop=True)


def run(cutoff="2025-11-24", sds=(0.0, 0.1, 0.15, 0.2, 0.3), season=2025, n=4000):
    m = load_matches(); cut = pd.Timestamp(cutoff)
    tm = TeamModel().fit(m[m.date < cut], asof=cut)
    out = {sd: {"title": [], "top4": [], "rel": []} for sd in sds}
    for lg, (name, nrel) in LEAGUES.items():
        s = m[(m.league == lg) & (m.season == season)]
        before, after = s[s.date < cut], s[s.date >= cut]
        if len(s) < 300 or before.empty:
            continue
        real = final_table(s); pos = {t: i for i, t in enumerate(real.team_id)}; T = len(real)
        for sd in sds:
            res = simulate_core(tm, table(before), after[["home_id", "away_id"]].to_dict("records"), domestic_bands(T, nrel), np.random.default_rng(3), n, sd)
            for r in res:
                i = pos[r["team_id"]]
                out[sd]["title"].append((r["title"], int(i == 0))); out[sd]["top4"].append((r["top4"], int(i < 4))); out[sd]["rel"].append((r["relegated"], int(i >= T - nrel)))
    print(f"Cutoff {cutoff}: simulate the rest of {season}-{(season + 1) % 100:02d} for 5 leagues, compare with the real final table")
    print("Brier score per team (lower is better):  title | top-4 | relegation")
    for sd, d in out.items():
        b = lambda k: np.mean([(p - h) ** 2 for p, h in d[k]])
        print(f"  strength uncertainty {sd:.2f}:  {b('title'):.4f} | {b('top4'):.4f} | {b('rel'):.4f}")
    # headline: what did the favourite get?
    return out


def run_champions_league(cutoff="2025-11-26", season=2025, last_day="2026-01-28", n=6000):
    """Pretend it is `cutoff` in last season's Champions League league phase; compare with the final league-phase table."""
    m = load_matches(); cut = pd.Timestamp(cutoff)
    tm = TeamModel().fit(m[m.date < cut], asof=cut)
    s = m[(m.league == "uefa.champions") & (m.season == season) & (m.date <= last_day)]
    before, after = s[s.date < cut], s[s.date >= cut]
    real = final_table(s); pos = {t: i for i, t in enumerate(real.team_id)}
    print(f"Champions League {season}-{(season + 1) % 100:02d}: {len(before)} matches played at cutoff, {len(after)} to come, {len(real)} teams")
    res = simulate_core(tm, table(before), after[["home_id", "away_id"]].to_dict("records"), CL_BANDS, np.random.default_rng(3), n, team_sd(table(before), m[m.date < cut], CL_SD, CL_NEW_SD))
    rows = []
    for r in res:
        i = pos[r["team_id"]]
        rows += [("top8", r["top8"], int(i < 8)), ("playoff", r["playoff"], int(8 <= i < 24)), ("out", r["out"], int(i >= 24))]
    d = pd.DataFrame(rows, columns=["band", "p", "hit"])
    print("Brier per team (lower is better), model vs a naive guess of 8/36, 16/36, 12/36 for everybody:")
    naive = {"top8": 8 / 36, "playoff": 16 / 36, "out": 12 / 36}
    for band, g in d.groupby("band"):
        print(f"  {band:8s} model {np.mean((g.p - g.hit) ** 2):.4f} | naive {np.mean((naive[band] - g.hit) ** 2):.4f}")
    d["b"] = pd.cut(d.p, [-.01, .05, .2, .5, .8, 1.01])
    print(d.groupby("b", observed=True).agg(n=("hit", "size"), said=("p", "mean"), actual=("hit", "mean")).round(2).to_string())


if __name__ == "__main__":
    if sys.argv[1:2] == ["cl"]:
        run_champions_league(*sys.argv[2:3]); raise SystemExit
    cutoff = sys.argv[1] if len(sys.argv) > 1 else "2025-11-24"
    o = run(cutoff)
    for sd in (0.0, 0.15):
        for k, label in (("top4", "top 4"), ("rel", "relegation")):
            d = pd.DataFrame(o[sd][k], columns=["p", "hit"]); d["b"] = pd.cut(d.p, [-.01, .05, .2, .5, .8, 1.01])
            print(f"\nsd {sd}, {label}: said vs actual"); print(d.groupby("b", observed=True).agg(n=("hit", "size"), said=("p", "mean"), actual=("hit", "mean")).round(2).to_string())
