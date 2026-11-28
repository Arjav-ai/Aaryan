"""Predictions for upcoming NFL / college football games -> data/predictions_nfl.json, data/predictions_cfb.json.

Usage: python -m betsuggester.us_predict [nfl|cfb ...]
Same file shape the NBA page already reads: games (with a score model for moneyline / spread / total) and players
(each with the stats they could be bet on, expected value and spread, and their last five games).
"""
import datetime as dt
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from . import espn
from . import us_model as M
from .us_ingest import LEAGUES

TAG = {"pass_yds": "Quarterback", "pass_td": "Quarterback", "rush_yds": "Ball carrier", "rec_yds": "Receiver", "rec": "Receiver"}
# how many players per team are offered for each kind of prop
TOP = {"pass_yds": 1, "rush_yds": 4, "rec_yds": 6}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum() or c == " ").replace(" jr", "").replace(" sr", "").replace(" iii", "").replace(" ii", "").strip()


def upcoming(league: str, days: int = 8) -> list[dict]:
    cfg = LEAGUES[league]; out, seen = [], set()
    today = dt.datetime.now(dt.timezone.utc).date()
    for d in range(-1, days):
        day = today + dt.timedelta(days=d)
        try:
            sb = espn.get(cfg["path"] + "/scoreboard", ttl=0, dates=day.strftime("%Y%m%d"), limit=400, **cfg["extra"])
        except Exception as e:
            print(f"  scoreboard {day}: skipped ({e})"); continue
        for ev in sb.get("events", []):
            if ev["status"]["type"]["state"] != "pre" or ev["id"] in seen:
                continue
            seen.add(ev["id"])
            side = {c["homeAway"]: c["team"] for c in ev["competitions"][0]["competitors"]}
            out.append({"id": ev["id"], "start": ev["date"], "date": ev["date"][:10], "home_id": side["home"]["id"], "away_id": side["away"]["id"],
                        "home": side["home"].get("abbreviation", ""), "away": side["away"].get("abbreviation", ""),
                        "home_name": side["home"]["displayName"], "away_name": side["away"]["displayName"]})
    return sorted(out, key=lambda g: g["start"])


def injuries(league: str) -> dict:
    if league != "nfl":
        return {}
    out = {}
    try:
        for tm in espn.get("football/nfl/injuries", ttl=0).get("injuries", []):
            for i in tm.get("injuries", []):
                out[norm(i["athlete"]["displayName"])] = {"status": i.get("status", ""), "note": i.get("shortComment", "")}
    except Exception as e:
        print("  injuries: skipped", e)
    return out


def main(league: str):
    g, p = M.load(league)
    asof = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
    games = upcoming(league)
    out = Path(f"data/predictions_{league}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "data_through": str(g.date.max().date()),
            "labels": M.STATS, "stats": M.STAT_ORDER}
    if not games:
        print(f"{league}: no upcoming games found; publishing an empty list")
        out.write_text(json.dumps({**meta, "games": [], "players": []})); return
    gm = M.fit_games(g, asof, **M.GAME_FIT[league])
    pj = M.Projector(g, p, league=league)
    inj = injuries(league)
    names = p.drop_duplicates("player_id", keep="last").set_index("player_id")["player"].to_dict()
    cutoff = {t: sorted(d)[-4:][0] for t, d in pj.team_dates.items()}
    cand = {}
    for r in p[p.date >= p.team_id.map(cutoff)].itertuples(index=False):
        cand.setdefault(r.team_id, set()).add(r.player_id)
    out_games, out_players, skipped = [], [], 0
    for gm_ in games:
        try:
            mh, ma = gm.expected_points(gm_["home_id"], gm_["away_id"])
            gm_["nba"] = {"mu_home": round(mh, 1), "mu_away": round(ma, 1), "mu_margin": round(mh - ma, 2), "mu_total": round(mh + ma, 1),
                          "sd_margin": M.SD_MARGIN[league], "sd_total": M.SD_TOTAL[league], "home_b2b": 0, "away_b2b": 0, "adj_margin": 0, "adj_notes": []}
        except KeyError:
            gm_["nba"] = None; skipped += 1            # a team the model has never seen (e.g. a small-college opponent): props only
        for team, opp, home, tabbr, oabbr in ((gm_["home_id"], gm_["away_id"], True, gm_["home"], gm_["away"]), (gm_["away_id"], gm_["home_id"], False, gm_["away"], gm_["home"])):
            cur = {}
            for pid in cand.get(team, ()):
                nm = names.get(pid, "")
                st = inj.get(norm(nm), {}).get("status", "")
                if st.lower().startswith("out"):
                    continue
                for stat in M.STAT_ORDER:
                    res = pj.project(pid, stat, team, opp, asof)
                    if res:
                        cur.setdefault(pid, {})[stat] = res[0]
            chosen = set()
            for key, k in TOP.items():
                ranked = sorted((pid for pid in cur if key in cur[pid]), key=lambda x: -cur[x][key])[:k]
                chosen.update(ranked)
            for pid in chosen:
                stats = {}
                for stat, mu in cur[pid].items():
                    if stat == "pass_td" and "pass_yds" not in cur[pid]:
                        continue
                    arr = pj.series[stat][pid]; arr = arr[arr[:, 0] < asof]
                    vals = [int(v) for v in arr[:, 1]]
                    stats[stat] = {"mu": round(float(mu), 2), "alpha": M.ALPHA[league][stat], "avg10": round(float(np.mean(vals[-8:])), 1), "last5": vals[-5:]}
                if not stats:
                    continue
                main = max(stats, key=lambda s: stats[s]["mu"] / max(pj.lg[s], 1e-9) if s in ("pass_yds", "rush_yds", "rec_yds") else 0)
                inf = inj.get(norm(names[pid]), {})
                out_players.append({"name": names[pid], "team": tabbr, "opp": oabbr, "home": home, "game": gm_["id"], "minutes": None, "tag": TAG[main],
                                    "stats": stats, "status": (inf.get("status") or None), "note": (inf.get("note") or None), "teammates_out": [], "teammates_out_pts": 0})
        out_games.append(gm_)
    out.write_text(json.dumps({**meta, "games": out_games, "players": out_players}, separators=(",", ":")))
    print(f"wrote {out}: {len(out_games)} games ({skipped} without a score model), {len(out_players)} players, {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    for lg in sys.argv[1:] or ["nfl", "cfb"]:
        main(lg)
