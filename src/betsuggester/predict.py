"""Make predictions for upcoming NBA games and write data/predictions.json.

Usage: python -m betsuggester.predict
Needs: games already downloaded (betsuggester.ingest). Pulls the schedule and injury list from ESPN.
"""
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from .features import (ABSENCE_WINDOW, FEATURES, ROTATION_MINUTES, absence_numbers, add_features,
                       load_player_games, rotation_snapshot)
from .model import STATS, fit_calibrated

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
OUT = Path("data/predictions.json")
# ESPN abbreviation -> Basketball-Reference abbreviation (only the ones that differ)
ESPN_TO_BBR = {"BKN": "BRK", "CHA": "CHO", "GS": "GSW", "NO": "NOP", "NY": "NYK", "PHX": "PHO", "SA": "SAS", "WSH": "WAS"}
STAT_LABEL = {"pts": "Points", "reb": "Rebounds", "ast": "Assists", "fg3": "Threes"}


def norm(name: str) -> str:
    """'Nikola Jokić Jr.' -> 'nikola jokic' so ESPN and Basketball-Reference names match."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.']", "", s)
    return re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).replace("-", " ").strip()


def get_json(url: str, **params) -> dict:
    r = requests.get(url, params=params, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def upcoming_games(days: int = 2) -> list[dict]:
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    games = []
    for d in range(days):
        day = today + dt.timedelta(days=d)
        for ev in get_json(f"{ESPN}/scoreboard", dates=day.strftime("%Y%m%d"))["events"]:
            if ev["status"]["type"]["state"] != "pre":
                continue  # already started or finished
            comp = ev["competitions"][0]["competitors"]
            side = {c["homeAway"]: c["team"]["abbreviation"] for c in comp}
            code = lambda a: ESPN_TO_BBR.get(a, a)
            games.append({"id": ev["id"], "start": ev["date"], "home": code(side["home"]), "away": code(side["away"]),
                          "date": pd.Timestamp(ev["date"]).tz_convert("America/New_York").date().isoformat()})
    return games


def injury_list() -> dict[str, dict]:
    out = {}
    for team in get_json(f"{ESPN}/injuries")["injuries"]:
        for i in team["injuries"]:
            out[norm(i["athlete"]["displayName"])] = {"status": i["status"], "note": i.get("shortComment", "")}
    return out


def main():
    hist = load_player_games()
    games = upcoming_games()
    if not games:
        raise SystemExit("No upcoming NBA games found right now.")
    injuries = injury_list()
    names = (hist.drop_duplicates(["team", "is_home"]).assign(full=lambda d: np.where(d.is_home == 1, d.home_team, d.away_team))
             .set_index("team")["full"].to_dict())
    last_date = hist.date.max()
    print(f"history through {last_date.date()}; {len(games)} upcoming games")

    # Who is in each team's rotation right now (last 10 team games), and who among them is ruled out?
    first = add_features(hist, "pts")  # gives min_post10 / stat_post10 for the snapshot
    rows, teams_info = [], {}
    for g in games:
        for team, opp, home in ((g["home"], g["away"], 1), (g["away"], g["home"], 0)):
            tdf = first[first.team == team]
            recent = list(dict.fromkeys(tdf.game_id))[-ABSENCE_WINDOW:]
            tdf = tdf[tdf.game_id.isin(recent)].sort_values(["date", "game_id"])
            rot = rotation_snapshot(tdf[["player", "min_post10", "stat_post10"]].itertuples(index=False, name=None))
            out_names = {p for p in rot if injuries.get(norm(p), {}).get("status", "").lower().startswith("out")}
            absent = absence_numbers(rot, out_names)
            teams_info[(g["id"], team)] = {"out": sorted(out_names), **absent}
            for p, (mn, st) in rot.items():
                if p in out_names:
                    continue
                rows.append({"game_id": f"UPC_{g['id']}", "team": team, "is_home": home, "player": p, "minutes": np.nan,
                             "pts": np.nan, "reb": np.nan, "ast": np.nan, "fg3": np.nan, "stl": np.nan, "blk": np.nan, "tov": np.nan,
                             "date": pd.Timestamp(g["date"]), "season": 2027,
                             "home_team": names[g["home"]], "away_team": names[g["away"]],
                             "opp": names[opp], "_gid": g["id"]})
    upc = pd.DataFrame(rows)

    players = {}
    for stat in STATS:
        full = pd.concat([hist, upc], ignore_index=True)
        feats = add_features(full, stat)
        train = feats.dropna(subset=FEATURES)
        train = train[(train.games_prior >= 5) & (train.min_avg10 >= 15) & train.game_id.map(lambda x: not x.startswith("UPC_"))]
        model = fit_calibrated(train, stat)
        cand = feats[feats.game_id.str.startswith("UPC_")]
        cand = cand[(cand.games_prior >= 5) & (cand.min_avg10 >= 15)].dropna(subset=FEATURES)
        cand = cand.assign(mu=model.mean(cand))
        for _, r in cand.iterrows():
            key = (r["_gid"], r.player)
            p = players.setdefault(key, {
                "name": r.player, "team": r.team, "opp": next(x for x in (g["away"] if g["home"] == r.team else g["home"] for g in games if g["id"] == r["_gid"])),
                "home": bool(r.is_home), "game": r["_gid"], "minutes": round(float(r.min_avg10), 1), "stats": {}})
            recent = hist[hist.player == r.player].sort_values("date")[stat].tail(5).astype(int).tolist()
            p["stats"][stat] = {"mu": round(float(r.mu), 2), "alpha": round(float(model.alpha), 4),
                                "avg10": round(float(r.stat_avg10), 1), "last5": recent}
        print(f"{stat}: {len(cand)} players, spread alpha={model.alpha:.3f}")

    for p in players.values():
        inj = injuries.get(norm(p["name"]))
        p["status"] = inj["status"] if inj else None
        p["note"] = inj["note"] if inj else None
        info = teams_info[(p["game"], p["team"])]
        p["teammates_out"] = info["out"]
        p["teammates_out_pts"] = round(info["out_stat"], 1)

    result = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "data_through": str(last_date.date()),
        "games": [{**g, "home_name": names[g["home"]], "away_name": names[g["away"]]} for g in games],
        "labels": STAT_LABEL,
        "players": sorted(players.values(), key=lambda p: (p["game"], p["team"], -p["minutes"])),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, separators=(",", ":")))
    print(f"wrote {OUT}: {len(result['players'])} players in {len(games)} games")


if __name__ == "__main__":
    main()
