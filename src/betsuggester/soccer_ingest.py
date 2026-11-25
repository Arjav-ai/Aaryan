"""Download football (soccer) matches and player box scores from ESPN into the local database.

Usage: python -m betsuggester.soccer_ingest [first_month]     e.g. 202508 (default: last season's start)
Safe to re-run: finished matches already saved are skipped.
"""
import datetime as dt
import sys
from concurrent.futures import ThreadPoolExecutor

from . import espn
from .db import connect

LEAGUES = {"eng.1": "Premier League", "esp.1": "La Liga", "ger.1": "Bundesliga",
           "ita.1": "Serie A", "fra.1": "Ligue 1", "uefa.champions": "Champions League",
           "uefa.europa": "Europa League", "uefa.europa.conf": "Conference League"}
ESPN_PATH = "soccer/{league}"


def months(first: str):
    y, m = int(first[:4]), int(first[4:])
    today = dt.date.today()
    while (y, m) <= (today.year, today.month):
        yield f"{y}{m:02d}", (y, m) == (today.year, today.month)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def parse_match(ev: dict, league: str) -> dict | None:
    if not ev["status"]["type"]["completed"]:
        return None
    comp = {c["homeAway"]: c for c in ev["competitions"][0]["competitors"]}
    try:
        hg, ag = int(comp["home"]["score"]), int(comp["away"]["score"])
    except (KeyError, ValueError):
        return None
    return {"match_id": ev["id"], "league": league, "season": ev["season"]["year"], "date": ev["date"][:10],
            "home_id": comp["home"]["team"]["id"], "home": comp["home"]["team"]["displayName"],
            "away_id": comp["away"]["team"]["id"], "away": comp["away"]["team"]["displayName"],
            "home_goals": hg, "away_goals": ag}


def parse_players(summary: dict, match: dict) -> list[dict]:
    rows = []
    for side in summary.get("rosters", []):
        home = side["homeAway"] == "home"
        for p in side.get("roster", []):
            st = {s["name"]: s["value"] for s in p.get("stats", [])}
            if not (p.get("starter") or p.get("subbedIn") or st.get("appearances")):
                continue  # unused substitute
            rows.append({
                "match_id": match["match_id"], "league": match["league"], "date": match["date"],
                "team_id": match["home_id"] if home else match["away_id"], "team": match["home"] if home else match["away"],
                "is_home": int(home), "player_id": p["athlete"]["id"], "player": p["athlete"]["displayName"],
                "pos": (p.get("position") or {}).get("abbreviation"), "starter": int(bool(p.get("starter"))),
                "sub_in": int(bool(p.get("subbedIn"))), "sub_out": int(bool(p.get("subbedOut"))),
                "shots": int(st.get("totalShots", 0)), "sot": int(st.get("shotsOnTarget", 0)),
                "goals": int(st.get("totalGoals", 0)), "assists": int(st.get("goalAssists", 0)),
                "fouls": int(st.get("foulsCommitted", 0)), "fouled": int(st.get("foulsSuffered", 0)),
                "yellow": int(st.get("yellowCards", 0)), "saves": int(st.get("saves", 0))})
    return rows


def ingest(first_month="202508"):
    conn = connect()
    have_players = {r[0] for r in conn.execute("SELECT DISTINCT match_id FROM soccer_player_games")}
    have_matches = {r[0] for r in conn.execute("SELECT match_id FROM soccer_matches")}
    for league, name in LEAGUES.items():
        new = 0
        for month, current in months(first_month):
            sb = espn.get(ESPN_PATH.format(league=league) + "/scoreboard", ttl=3600 if current else None, dates=month)
            matches = []
            for ev in sb.get("events", []):
                m = parse_match(ev, league)
                if m:
                    matches.append(m)
            for m in matches:
                if m["match_id"] not in have_matches:
                    with conn:
                        conn.execute("INSERT OR REPLACE INTO soccer_matches VALUES (:match_id,:league,:season,:date,:home_id,:home,:away_id,:away,:home_goals,:away_goals)", m)
                    have_matches.add(m["match_id"])
                    new += 1
            todo = [m for m in matches if m["match_id"] not in have_players]
            with ThreadPoolExecutor(8) as pool:   # 8 downloads at once; ESPN copes fine
                summaries = list(pool.map(lambda m: espn.get(ESPN_PATH.format(league=league) + "/summary", pace=False, event=m["match_id"]), todo))
            for m, summ in zip(todo, summaries):
                rows = parse_players(summ, m)
                with conn:
                    conn.executemany("INSERT OR REPLACE INTO soccer_player_games VALUES (:match_id,:league,:date,:team_id,:team,:is_home,:player_id,:player,:pos,:starter,:sub_in,:sub_out,:shots,:sot,:goals,:assists,:fouls,:fouled,:yellow,:saves)", rows)
                have_players.add(m["match_id"])
            print(f"{name} {month}: {new} new matches so far", flush=True)
    print("done")


if __name__ == "__main__":
    ingest(sys.argv[1] if len(sys.argv) > 1 else "202508")
