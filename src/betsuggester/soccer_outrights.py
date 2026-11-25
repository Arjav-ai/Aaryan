"""League outrights: simulate the rest of each domestic season many times using the match model,
then count how often each team wins the league, finishes top 4, or is relegated."""
import numpy as np
import pandas as pd

from . import espn
from .soccer_model import MAX_GOALS, TeamModel

LEAGUES = {"eng.1": ("Premier League", 3), "esp.1": ("La Liga", 3), "ger.1": ("Bundesliga", 2),
           "ita.1": ("Serie A", 3), "fra.1": ("Ligue 1", 2)}   # name, number relegated (direct)
N_SIMS = 20000


def remaining_fixtures(league: str, season_year: int, months) -> list[dict]:
    out = []
    for ym in months:
        for ev in espn.get(f"soccer/{league}/scoreboard", ttl=3600, dates=ym).get("events", []):
            if ev["status"]["type"]["completed"] or ev["season"]["year"] != season_year:
                continue
            c = {x["homeAway"]: x["team"] for x in ev["competitions"][0]["competitors"]}
            out.append({"home_id": c["home"]["id"], "away_id": c["away"]["id"], "date": ev["date"][:10]})
    return out


def table(matches: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for r in matches.itertuples(index=False):
        for tid, name, gf, ga in ((r.home_id, r.home, r.home_goals, r.away_goals), (r.away_id, r.away, r.away_goals, r.home_goals)):
            t = rows.setdefault(tid, {"team_id": tid, "team": name, "played": 0, "points": 0, "gf": 0, "ga": 0})
            t["played"] += 1; t["gf"] += gf; t["ga"] += ga
            t["points"] += 3 if gf > ga else 1 if gf == ga else 0
    return pd.DataFrame(rows.values())


STRENGTH_SD = 0.15   # how unsure we are of each team's attack and defence (log scale); see retro_test
NEW_TEAM_SD = 0.30   # ...for clubs we have little data on (e.g. Champions League newcomers)
CL_LEAGUE_PHASE_END = "2027-01-28"   # last league-phase match day (so later matches are knockouts)


def domestic_bands(T, nrel):
    return {"title": (0, 1), "top4": (0, 4), "relegated": (T - nrel, T)}


CL_BANDS = {"top8": (0, 8), "playoff": (8, 24), "out": (24, 36)}
CL_SD, CL_NEW_SD = 0.35, 0.50   # league-phase results are noisy: tuned on last season at 3 cutoffs (see soccer_retro cl)


def team_sd(tab, matches, base=STRENGTH_SD, new=NEW_TEAM_SD, min_matches=12):
    n = pd.concat([matches.home_id, matches.away_id]).value_counts()
    return np.array([new if n.get(t, 0) < min_matches else base for t in tab.team_id])


def simulate_core(model, tab, fixtures, bands, rng, n=N_SIMS, sd=STRENGTH_SD):
    """tab: table() output. fixtures: remaining matches [{home_id, away_id}].
    bands: {name: (first_rank, last_rank_exclusive)} -> chance of finishing in that band (rank 0 = top).
    sd: one number or a per-team array. Returns one dict per team."""
    idx = {t: i for i, t in enumerate(tab.team_id)}
    T = len(tab)
    sd = np.broadcast_to(np.asarray(sd, dtype=float), (T,))
    pts = np.tile(tab.points.to_numpy(float), (n, 1)); gd = np.tile((tab.gf - tab.ga).to_numpy(float), (n, 1))
    gf = np.tile(tab.gf.to_numpy(float), (n, 1))
    # each simulated season gets its own "true strength" for every team: the model's estimate plus uncertainty
    eps_att, eps_def = rng.normal(0, 1, (n, T)) * sd, rng.normal(0, 1, (n, T)) * sd
    for f in fixtures:
        if f["home_id"] not in idx or f["away_id"] not in idx:
            continue
        h, a = idx[f["home_id"]], idx[f["away_id"]]
        lh, la = model.expected_goals(f["home_id"], f["away_id"])
        hg = rng.poisson(lh * np.exp(eps_att[:, h] + eps_def[:, a])); ag = rng.poisson(la * np.exp(eps_att[:, a] + eps_def[:, h]))
        pts[:, h] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0)); pts[:, a] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
        gd[:, h] += hg - ag; gd[:, a] += ag - hg; gf[:, h] += hg; gf[:, a] += ag
    score = pts * 1e6 + gd * 1e3 + gf + rng.random((n, T)) * 0.5      # points, goal difference, goals, coin flip
    rank = (-score).argsort(axis=1).argsort(axis=1)                  # 0 = top of the table
    res = []
    for i, t in enumerate(tab.itertuples(index=False)):
        row = {"team_id": t.team_id, "team": t.team, "played": int(t.played), "points": int(t.points),
               "exp_points": round(float(pts[:, i].mean()), 1)}
        for name, (lo, hi) in bands.items():
            row[name] = round(float(((rank[:, i] >= lo) & (rank[:, i] < hi)).mean()), 4)
        res.append(row)
    first = next(iter(bands))
    return sorted(res, key=lambda r: (-r[first], -r["exp_points"]))


def simulate(league, model, matches, season_year, rng=None, n=N_SIMS, sd=STRENGTH_SD):
    """Domestic league: title / top 4 / relegation."""
    rng = rng or np.random.default_rng(7)
    cur = matches[(matches.league == league) & (matches.season == season_year)]
    months = pd.period_range(pd.Timestamp.today(), periods=9, freq="M").strftime("%Y%m")
    tab = table(cur)
    return simulate_core(model, tab, remaining_fixtures(league, season_year, months),
                         domestic_bands(len(tab), LEAGUES[league][1]), rng, n, sd)


def simulate_champions_league(model, matches, season_year, rng=None, n=N_SIMS):
    """League phase only: top 8 (straight to last 16), playoff places 9-24, eliminated 25-36.
    Trophy chances are NOT simulated: they depend on knockout draws that have not happened yet."""
    rng = rng or np.random.default_rng(5)
    cur = matches[(matches.league == "uefa.champions") & (matches.season == season_year) & (matches.date <= CL_LEAGUE_PHASE_END)]
    months = pd.period_range(pd.Timestamp.today(), periods=4, freq="M").strftime("%Y%m")
    fixtures = [f for f in remaining_fixtures("uefa.champions", season_year, months) if f["date"] <= CL_LEAGUE_PHASE_END]
    tab = table(cur)
    return simulate_core(model, tab, fixtures, CL_BANDS, rng, n, team_sd(tab, matches, CL_SD, CL_NEW_SD))
