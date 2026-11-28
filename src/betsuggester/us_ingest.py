"""Download NFL and college football (FBS) games and player box scores from ESPN into the local database.

Usage: python -m betsuggester.us_ingest
Safe to re-run: finished games already saved are skipped, and only the weeks that can still hold new games are fetched.
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from . import espn
from .db import connect

LEAGUES = {"nfl": {"path": "football/nfl", "extra": {}, "seasons": [2025, 2026], "weeks": range(1, 19), "name": "NFL"},
           "cfb": {"path": "football/college-football", "extra": {"groups": 80}, "seasons": [2025, 2026], "games_only": [2025], "weeks": range(1, 16), "name": "College football"}}


def _num(x, default=0):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def parse_game(ev: dict, league: str, season: int, week: int) -> dict | None:
    if not ev["status"]["type"]["completed"]:
        return None
    comp = ev["competitions"][0]
    side = {c["homeAway"]: c for c in comp["competitors"]}
    try:
        hp, ap = int(side["home"]["score"]), int(side["away"]["score"])
    except (KeyError, ValueError):
        return None
    t = lambda s, k: side[s]["team"].get(k)
    return {"game_id": ev["id"], "league": league, "season": season, "week": week, "date": ev["date"][:10],
            "home_id": t("home", "id"), "home": t("home", "displayName"), "home_abbr": t("home", "abbreviation"),
            "away_id": t("away", "id"), "away": t("away", "displayName"), "away_abbr": t("away", "abbreviation"),
            "home_pts": hp, "away_pts": ap, "neutral": int(bool(comp.get("neutralSite"))), "spread": None, "total": None}


def parse_players(summary: dict, g: dict) -> list[dict]:
    rows = {}
    for tm in summary.get("boxscore", {}).get("players", []):
        tid = tm["team"]["id"]
        for cat in tm.get("statistics", []):
            labels = cat.get("labels", [])
            for a in cat.get("athletes", []):
                st = dict(zip(labels, a.get("stats", [])))
                r = rows.setdefault((tid, a["athlete"]["id"]), {
                    "game_id": g["game_id"], "league": g["league"], "date": g["date"], "team_id": tid, "team": tm["team"]["displayName"],
                    "is_home": int(tid == g["home_id"]), "player_id": a["athlete"]["id"], "player": a["athlete"]["displayName"],
                    "pass_att": 0, "pass_yds": 0, "pass_td": 0, "pass_int": 0, "rush_att": 0, "rush_yds": 0, "rush_td": 0,
                    "rec": 0, "rec_yds": 0, "rec_td": 0, "targets": 0})
                if cat["name"] == "passing":
                    att = str(st.get("C/ATT", "0/0")).split("/")
                    r.update(pass_att=_num(att[-1]), pass_yds=_num(st.get("YDS")), pass_td=_num(st.get("TD")), pass_int=_num(st.get("INT")))
                elif cat["name"] == "rushing":
                    r.update(rush_att=_num(st.get("CAR")), rush_yds=_num(st.get("YDS")), rush_td=_num(st.get("TD")))
                elif cat["name"] == "receiving":
                    r.update(rec=_num(st.get("REC")), rec_yds=_num(st.get("YDS")), rec_td=_num(st.get("TD")), targets=_num(st.get("TGTS")))
    return list(rows.values())


def parse_lines(summary: dict) -> tuple[float | None, float | None]:
    """Pre-game spread (home team's line; negative = home favoured) and total from the summary's pick centre."""
    for pc in summary.get("pickcenter", []) or []:
        sp, tot = pc.get("spread"), pc.get("overUnder")
        if sp is not None or tot is not None:
            return (float(sp) if sp is not None else None, float(tot) if tot is not None else None)
    return None, None


def ingest():
    conn = connect()
    have_players = {r[0] for r in conn.execute("SELECT DISTINCT game_id FROM us_player_games")}
    have_games = {r[0] for r in conn.execute("SELECT game_id FROM us_games")}
    for league, cfg in LEAGUES.items():
        for season in cfg["seasons"]:
            last = conn.execute("SELECT MAX(week) FROM us_games WHERE league=? AND season=?", (league, season)).fetchone()[0]
            first_week = max(1, (last or 1) - 1) if season == max(cfg["seasons"]) else (1 if last is None else 99)
            for week in cfg["weeks"]:
                if week < first_week:
                    continue
                sb = espn.get(cfg["path"] + "/scoreboard", ttl=1800, dates=str(season), seasontype=2, week=week, limit=400, **cfg["extra"])
                games = [g for g in (parse_game(ev, league, season, week) for ev in sb.get("events", [])) if g]
                if season in cfg.get("games_only", []):      # last season: scores only (priors for the team ratings), no box scores
                    with conn:
                        conn.executemany("INSERT OR IGNORE INTO us_games VALUES (:game_id,:league,:season,:week,:date,:home_id,:home,:home_abbr,:away_id,:away,:away_abbr,:home_pts,:away_pts,:neutral,:spread,:total)", games)
                    continue
                todo = [g for g in games if g["game_id"] not in have_players]
                with ThreadPoolExecutor(8) as pool:
                    sums = list(pool.map(lambda g: espn.get(cfg["path"] + "/summary", pace=False, event=g["game_id"]), todo))
                for g, s in zip(todo, sums):
                    g["spread"], g["total"] = parse_lines(s)
                    rows = parse_players(s, g)
                    with conn:
                        conn.execute("INSERT OR REPLACE INTO us_games VALUES (:game_id,:league,:season,:week,:date,:home_id,:home,:home_abbr,:away_id,:away,:away_abbr,:home_pts,:away_pts,:neutral,:spread,:total)", g)
                        conn.executemany("INSERT OR REPLACE INTO us_player_games VALUES (:game_id,:league,:date,:team_id,:team,:is_home,:player_id,:player,:pass_att,:pass_yds,:pass_td,:pass_int,:rush_att,:rush_yds,:rush_td,:rec,:rec_yds,:rec_td,:targets)", rows)
                    have_players.add(g["game_id"]); have_games.add(g["game_id"])
                if todo:
                    print(f"{cfg['name']} {season} week {week}: {len(todo)} new games", flush=True)
    print("done")


if __name__ == "__main__":
    ingest()
