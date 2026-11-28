"""Mark the frozen predictions (prediction_log.json) against real results -> data/scorecard.json for the page's
"Model record" screen. Also carries the headline numbers from the walk-forward tests, so the page can show both.

Usage: python -m betsuggester.scorecard
"""
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .db import connect

OUT = Path("data/scorecard.json")
LOG = Path("data/prediction_log.json")
BINS = [(0, .3), (.3, .45), (.45, .55), (.55, .7), (.7, 1.01)]
NAMES = {"nba": "NBA", "nfl": "NFL", "cfb": "College football", "tennis": "Tennis", "football": "Football (soccer)"}
STAT_NAMES = {"pts": "Points", "reb": "Rebounds", "ast": "Assists", "fg3": "Threes", "shots": "Shots", "sot": "Shots on target", "goals": "Goals", "assists": "Assists",
              "pass_yds": "Passing yards", "pass_td": "Passing TDs", "rush_yds": "Rushing yards", "rec_yds": "Receiving yards", "rec": "Receptions"}

# Headline results of the walk-forward tests (on games the models had not seen), as written in the README and the page.
TESTED = {
    "nba": ["Props: when the model said 70-80% the prop hit about 73% of the time (above 90%: 86-94%).",
            "Games: winner picked 69% of the time over about 1,000 games; typical margin miss 14.9 points vs the bookmaker's 14.0. Bookmaker lines are better.",
            "Betting every gap against the bookmaker's line would have lost about 2% per bet."],
    "nfl": ["Games (104 games): winner 62% (bookmaker 71%); margin miss 12.3 vs 11.8 points. Bookmaker lines are better.",
            "Props (7,400 player-games): chances matched what happened, but only slightly beat giving every player in a role the league average."],
    "cfb": ["Games (507 games): winner 68% (bookmaker 71%); margin miss 16.0 vs 15.1 points. Bookmaker lines are better.",
            "Props (10,000 player-games): chances matched what happened, but only slightly beat the league average for each role."],
    "tennis": ["Match winner (2026, ATP 3,365 / WTA 5,509 matches): 63% / 62% winners picked; log-loss 0.637 / 0.641 (a coin flip is 0.693).",
               "Total games and handicap: matched near the middle of the range, 5-10 points off far from it. No bookmaker prices to compare with."],
    "football": ["1,400 matches: win/draw/loss probabilities clearly beat league-average guesses; total goals is the weakest market.",
                 "Shots and shots on target were well calibrated over 28,000 player-games; goals and assists are rougher."]}


def nb_sf(mu, alpha, line):
    r = 1.0 / alpha
    return float(stats.nbinom.sf(math.floor(line), r, r / (r + mu)))


def bins_table(pred, act, minimum=1):
    rows = []
    pred, act = np.asarray(pred, float), np.asarray(act, float)
    for lo, hi in BINS:
        k = (pred >= lo) & (pred < hi)
        if k.sum() >= minimum:
            rows.append({"band": f"{round(lo*100)}-{min(round(hi*100),100)}%", "n": int(k.sum()), "said": round(float(pred[k].mean()), 3), "happened": round(float(act[k].mean()), 3)})
    return rows


def results_index(conn):
    """key -> actual result, for every sport: game outcome and player stats."""
    idx = {}
    # NBA: date|home code
    g = pd.read_sql_query("""SELECT g.game_id, g.date, g.home_pts, g.away_pts, hp.team AS home FROM games g
        JOIN (SELECT DISTINCT game_id, team FROM player_games WHERE is_home = 1) hp USING (game_id)""", conn)
    pl = pd.read_sql_query("SELECT game_id, player, pts, reb, ast, fg3 FROM player_games", conn)
    by = {k: x for k, x in pl.groupby("game_id")}
    for r in g.itertuples(index=False):
        p = by.get(r.game_id)
        idx[f"nba:{r.date}|{r.home}"] = {"hp": r.home_pts, "ap": r.away_pts, "players": {x.player: {"pts": x.pts, "reb": x.reb, "ast": x.ast, "fg3": x.fg3} for x in p.itertuples()} if p is not None else {}}
    # US football
    for lg in ("nfl", "cfb"):
        g = pd.read_sql_query("SELECT game_id, home_pts, away_pts FROM us_games WHERE league=?", conn, params=(lg,))
        pl = pd.read_sql_query("SELECT game_id, player, pass_yds, pass_td, rush_yds, rec_yds, rec FROM us_player_games WHERE league=?", conn, params=(lg,))
        by = {k: x for k, x in pl.groupby("game_id")}
        for r in g.itertuples(index=False):
            p = by.get(r.game_id)
            idx[f"{lg}:{r.game_id}"] = {"hp": r.home_pts, "ap": r.away_pts, "players": {x.player: {s: getattr(x, s) for s in ("pass_yds", "pass_td", "rush_yds", "rec_yds", "rec")} for x in p.itertuples()} if p is not None else {}}
    # football (soccer)
    g = pd.read_sql_query("SELECT match_id, home_goals, away_goals FROM soccer_matches", conn)
    pl = pd.read_sql_query("SELECT match_id, player, shots, sot, goals, assists FROM soccer_player_games", conn)
    by = {k: x for k, x in pl.groupby("match_id")}
    for r in g.itertuples(index=False):
        p = by.get(r.match_id)
        idx[f"football:{r.match_id}"] = {"hp": r.home_goals, "ap": r.away_goals, "players": {x.player: {s: getattr(x, s) for s in ("shots", "sot", "goals", "assists")} for x in p.itertuples()} if p is not None else {}}
    # tennis
    t = pd.read_sql_query("SELECT match_id, games1, games2, sets1, sets2, status FROM tennis_matches WHERE state='post'", conn)
    for r in t.itertuples(index=False):
        if r.status == "Final":
            idx[f"tennis:{r.match_id}"] = {"hp": r.games1, "ap": r.games2, "sets_h": r.sets1, "sets_a": r.sets2, "players": {}}
    return idx


def main():
    log = json.loads(LOG.read_text()) if LOG.exists() else {"games": {}, "props": {}}
    idx = results_index(connect())
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    out = {"generated_at": now, "since": None, "sports": {}}
    starts = [e["start"] for e in log["games"].values()]
    out["since"] = min(starts)[:10] if starts else None
    for sport in NAMES:
        s = {"name": NAMES[sport], "tested": TESTED[sport], "settled": 0, "logged": 0}
        py, pd_, py_all, ey, over_pred, over_act, tot_err, mu_tot = [], [], [], [], [], [], [], []
        pr_pred, pr_act, per_stat = [], [], {}
        for key, e in log["games"].items():
            if e["sport"] != sport:
                continue
            s["logged"] += 1
            if sport == "nba": rk = f"nba:{e['date']}|{e['home']}"
            elif sport in ("nfl", "cfb", "football", "tennis"): rk = f"{sport}:{e['id']}"
            res = idx.get(rk)
            if not res:
                continue
            s["settled"] += 1
            hp, ap = float(res["hp"]), float(res["ap"])
            if sport == "tennis":
                home_won = res["sets_h"] > res["sets_a"]
            else:
                if hp == ap and sport != "football":
                    continue
                home_won = hp > ap
            py.append(e["p_home"]); ey.append(1.0 if home_won else 0.0)
            if sport == "football":
                draw = 1.0 if hp == ap else 0.0
                pd_.append((e["p_home"], e["p_draw"], 1 - e["p_home"] - e["p_draw"], 0 if home_won else (1 if draw else 2)))
            total = hp + ap
            if "sd_total" in e:
                line = math.floor(e["mu_total"]) + 0.5
                over_pred.append(1 - stats.norm.cdf((line - e["mu_total"]) / e["sd_total"])); over_act.append(1.0 if total > line else 0.0)
            tot_err.append(total - e["mu_total"]); mu_tot.append(e["mu_total"])
            for name, stat, mu, alpha in log["props"].get(key, []):
                pv = res["players"].get(name)
                if pv is None or stat not in pv:
                    continue
                line = math.floor(mu) + 0.5
                p_over = nb_sf(mu, alpha, line)
                pr_pred.append(p_over); pr_act.append(1.0 if pv[stat] > line else 0.0)
                st = per_stat.setdefault(stat, {"n": 0, "pred": 0.0, "act": 0.0, "mu": 0.0, "y": 0.0})
                st["n"] += 1; st["pred"] += p_over; st["act"] += 1.0 if pv[stat] > line else 0.0; st["mu"] += mu; st["y"] += float(pv[stat])
        n = len(py)
        if n:
            p = np.clip(np.array(py), 0.001, 0.999); y = np.array(ey)
            s["games"] = {"n": n, "winner_right": round(float(((p > .5) == (y == 1)).mean()), 3), "brier": round(float(((p - y) ** 2).mean()), 4), "brier_coin": 0.25,
                          "logloss": round(float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()), 4), "bins": bins_table(p, y)}
            if sport == "football" and pd_:
                a = np.array(pd_); pr3 = np.clip(a[np.arange(len(a)), a[:, 3].astype(int)], 0.001, 1)
                s["games"]["logloss3"] = round(float(-np.log(pr3).mean()), 4); s["games"]["logloss3_guess"] = 1.0986
            if over_pred:
                s["totals"] = {"n": len(over_pred), "said_over": round(float(np.mean(over_pred)), 3), "happened_over": round(float(np.mean(over_act)), 3), "miss": round(float(np.mean(tot_err)), 2), "expected_avg": round(float(np.mean(mu_tot)), 2)}
        if pr_pred:
            s["props"] = {"n": len(pr_pred), "bins": bins_table(pr_pred, pr_act, minimum=5), "said_over": round(float(np.mean(pr_pred)), 3), "happened_over": round(float(np.mean(pr_act)), 3),
                          "stats": [{"stat": STAT_NAMES.get(k, k), "n": v["n"], "said_over": round(v["pred"] / v["n"], 3), "happened_over": round(v["act"] / v["n"], 3), "expected": round(v["mu"] / v["n"], 2), "actual": round(v["y"] / v["n"], 2)} for k, v in per_stat.items() if v["n"] >= 10]}
        out["sports"][sport] = s
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print("scorecard:", {k: (v["settled"], v["logged"]) for k, v in out["sports"].items()}, f"since {out['since']}")


if __name__ == "__main__":
    main()
