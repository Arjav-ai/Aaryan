"""Write data/predictions_soccer.json: upcoming matches (full scoreline grid), player props, league outrights.

Usage: python -m betsuggester.soccer_predict
Run soccer_ingest first so results are up to date.
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import espn
from .model import fit_calibrated
from .soccer_ingest import LEAGUES as COMPETITIONS
from .soccer_model import TeamModel, load_matches
from .soccer_outrights import LEAGUES as DOMESTIC, simulate, simulate_champions_league
from .soccer_props import FEATURES, LABELS, LINES, REQUIRED, STATS, add_features, load_player_games

OUT = Path("data/predictions_soccer.json")
DAYS_AHEAD = 7


def knockout_draw_done() -> bool:
    """True once ESPN lists knockout-stage Champions League fixtures between named teams."""
    today = dt.datetime.now(dt.timezone.utc).date()
    for k in range(0, 8):
        ym = (pd.Timestamp(today) + pd.DateOffset(months=k)).strftime("%Y%m")
        for ev in espn.get("soccer/uefa.champions/scoreboard", ttl=3600, dates=ym).get("events", []):
            if ev.get("season", {}).get("slug", "league-phase") != "league-phase":
                names = [c["team"]["displayName"] for c in ev["competitions"][0]["competitors"]]
                if not any("winner" in n.lower() or "tbd" in n.lower() or "/" in n for n in names):
                    return True
    return False


def upcoming(days=DAYS_AHEAD) -> list[dict]:
    today = dt.datetime.now(dt.timezone.utc).date()
    months = sorted({(today + dt.timedelta(days=d)).strftime("%Y%m") for d in range(days + 1)})
    out = []
    for lg, name in COMPETITIONS.items():
        for ym in months:
            for ev in espn.get(f"soccer/{lg}/scoreboard", ttl=3600, dates=ym).get("events", []):
                st = ev["status"]["type"]
                when = pd.Timestamp(ev["date"])
                if st["completed"] or st["state"] != "pre" or not (pd.Timestamp(today, tz="UTC") <= when < pd.Timestamp(today + dt.timedelta(days=days), tz="UTC")):
                    continue
                c = {x["homeAway"]: x["team"] for x in ev["competitions"][0]["competitors"]}
                out.append({"id": ev["id"], "league": lg, "league_name": name, "start": ev["date"], "date": ev["date"][:10],
                            "home_id": c["home"]["id"], "home": c["home"]["displayName"], "away_id": c["away"]["id"], "away": c["away"]["displayName"]})
    return sorted(out, key=lambda m: m["start"])


def main():
    matches = load_matches()
    last = matches.date.max()
    games = upcoming()
    if not games:
        raise SystemExit("No upcoming football matches in the next week.")
    print(f"results through {last.date()}; {len(games)} matches in the next {DAYS_AHEAD} days")
    tm = TeamModel().fit(matches, asof=pd.Timestamp.today().normalize())

    for g in games:
        M = tm.score_matrix(g["home_id"], g["away_id"])
        g["xg_home"], g["xg_away"] = [round(x, 2) for x in tm.expected_goals(g["home_id"], g["away_id"])]
        g["grid"] = [[round(float(x), 5) for x in row] for row in M]   # grid[home goals][away goals]
        g["known"] = bool(g["home_id"] in tm.idx and g["away_id"] in tm.idx)

    # ---- player props (given the player plays) ----
    hist = load_player_games()
    by_team = {}
    for tid, grp in hist.sort_values("date").groupby("team_id"):
        by_team[tid] = grp
    rows = []
    for g in games:
        for tid, oid, home in ((g["home_id"], g["away_id"], 1), (g["away_id"], g["home_id"], 0)):
            grp = by_team.get(tid)
            if grp is None:
                continue
            recent = grp[grp.match_id.isin(list(dict.fromkeys(grp.match_id))[-5:])]
            for pid, p in recent.groupby("player_id"):
                rows.append({"match_id": f"UPC_{g['id']}", "league": g["league"], "date": pd.Timestamp(g["date"]), "team_id": tid,
                             "team": g["home"] if home else g["away"], "is_home": home, "player_id": pid, "player": p.player.iloc[-1],
                             "pos": None, "starter": np.nan, "sub_in": np.nan, "sub_out": np.nan, "shots": np.nan, "sot": np.nan, "goals": np.nan,
                             "assists": np.nan, "fouls": np.nan, "fouled": np.nan, "yellow": np.nan, "saves": np.nan,
                             "home_id": g["home_id"], "away_id": g["away_id"], "home_goals": np.nan, "away_goals": np.nan,
                             "opp_id": oid, "team_goals": np.nan, "opp_goals": np.nan, "pos_c": np.nan, "_gid": g["id"]})
    upc = pd.DataFrame(rows)
    players = {}
    for stat in STATS:
        feats = add_features(pd.concat([hist, upc], ignore_index=True), stat)
        past = feats[~feats.match_id.astype(str).str.startswith("UPC_")].dropna(subset=REQUIRED)
        past = past[(past.games_prior >= 5) & (past.pos_code > 0) & (past.start_rate10 >= 0.5)]
        model = fit_calibrated(past, stat, FEATURES, LINES[stat])
        cand = feats[feats.match_id.astype(str).str.startswith("UPC_")]
        cand = cand[(cand.games_prior >= 5) & (cand.pos_code > 0) & (cand.start_rate10 >= 0.5)].dropna(subset=REQUIRED)
        cand = cand.assign(mu=model.mean(cand))
        for _, r in cand.iterrows():
            key = (r["_gid"], r.player_id)
            p = players.setdefault(key, {"name": r.player, "team": r.team, "home": bool(r.is_home), "game": r["_gid"],
                                         "opp": next(g["away"] if g["home_id"] == r.team_id else g["home"] for g in games if g["id"] == r["_gid"]),
                                         "tag": f"Started {int(round(r.start_rate10 * 10))} of last 10", "stats": {}})
            recent = hist[hist.player_id == r.player_id].sort_values("date")[stat].tail(5).astype(int).tolist()
            p["stats"][stat] = {"mu": round(float(r.mu), 3), "alpha": round(float(model.alpha), 4), "avg10": round(float(r.stat_avg10), 2), "last5": recent}
        print(f"{stat}: {len(cand)} players, alpha={model.alpha:.3f}")

    # ---- outrights ----
    season = int(matches.season.max())
    outrights = {}
    rng = np.random.default_rng(11)
    for lg, (name, nrel) in DOMESTIC.items():
        teams = simulate(lg, tm, matches, season, rng)
        outrights[lg] = {"name": name, "teams": teams, "markets": [
            {"key": "title", "label": "Win the league", "note": "League winner."},
            {"key": "top4", "label": "Top 4", "note": "Top 4 finish."},
            {"key": "relegated", "label": "Relegated", "note": f"Bottom {nrel} go down."}]}
        print(f"{name}: favourite {teams[0]['team']} {teams[0]['title']:.0%} to win the league")

    # Champions League: league phase only. Trophy chances depend on knockout draws, so they are only
    # given once those draws have been made (nothing to show until ESPN lists knockout fixtures).
    cl = simulate_champions_league(tm, matches, season)
    knockout = knockout_draw_done()
    outrights["uefa.champions"] = {"name": "Champions League", "teams": cl, "markets": [
        {"key": "top8", "label": "Top 8", "note": "Top 8 skip the playoff and go straight to the last 16."},
        {"key": "playoff", "label": "Playoff (9-24)", "note": "Places 9 to 24 play off for the last 16. This middle band is the hardest to call: in testing the model did no better than a flat guess here."},
        {"key": "out", "label": "Out (25-36)", "note": "Bottom 12 are eliminated."}],
        "pending": ("The knockout draw has been made, but trophy chances for it have not been built yet: ask Claude."
                    if knockout else "Chances to win the trophy will be shown after the knockout draw. They depend on who is drawn against whom, which is not known yet.")}
    print(f"Champions League: league phase only (knockout draw done: {knockout}); most likely top 8: {cl[0]['team']} {cl[0]['top8']:.0%}")

    result = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "data_through": str(last.date()),
              "stats": STATS, "labels": LABELS, "games": games,
              "players": sorted(players.values(), key=lambda p: (p["game"], p["team"], p["name"])), "outrights": outrights}
    OUT.write_text(json.dumps(result, separators=(",", ":")))
    print(f"wrote {OUT}: {len(games)} matches, {len(result['players'])} players, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
