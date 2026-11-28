"""Live scores for today's NBA games and football matches -> data/live.json (takes a few seconds).

Usage: python -m betsuggester.live
Only today's scoreboards (UTC today and yesterday, so late games are not lost). No database, no model.
"""
import datetime as dt
import argparse
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import espn
from .soccer_ingest import LEAGUES

OUT = Path("data/live.json")
# ESPN team code -> the code used for the NBA crest files (kept here so this script needs no heavy libraries)
ESPN_TO_BBR = {"BKN": "BRK", "CHA": "CHO", "GS": "GSW", "NO": "NOP", "NY": "NYK", "PHX": "PHO", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}


def parse(ev: dict, sport: str, league: str, league_name: str) -> dict | None:
    try:
        comp = ev["competitions"][0]
        side = {c["homeAway"]: c for c in comp["competitors"]}
        st = ev["status"]
        row = {"sport": sport, "league": league, "league_name": league_name, "id": ev["id"], "start": ev["date"],
               "state": st["type"]["state"],               # pre / in / post
               "detail": st["type"].get("shortDetail") or st["type"].get("description", ""),
               "clock": st.get("displayClock", ""), "period": st.get("period", 0),
               "home_id": side["home"]["team"]["id"], "away_id": side["away"]["team"]["id"],
               "home_code": ESPN_TO_BBR.get(side["home"]["team"].get("abbreviation", ""), side["home"]["team"].get("abbreviation", "")),
               "away_code": ESPN_TO_BBR.get(side["away"]["team"].get("abbreviation", ""), side["away"]["team"].get("abbreviation", "")),
               "home": side["home"]["team"]["displayName"], "away": side["away"]["team"]["displayName"],
               "home_score": int(side["home"].get("score") or 0), "away_score": int(side["away"].get("score") or 0)}
    except (KeyError, ValueError, IndexError):
        return None
    return row


def fetch_one(args):
    sport, league, name, path, *rest = args
    extra = rest[0] if rest else {}
    out = []
    today = dt.datetime.now(dt.timezone.utc).date()
    for d in (today - dt.timedelta(days=1), today):
        try:
            sb = espn.get(path + "/scoreboard", ttl=0, pace=False, dates=d.strftime("%Y%m%d"), limit=400, **extra)
        except Exception as e:      # one league failing must not hide the others
            print(f"{name}: skipped ({e})")
            continue
        out += [r for r in (parse(ev, sport, league, name) for ev in sb.get("events", [])) if r]
    return out


def add_box_scores(games):
    """For games in play: how much of the game is gone and every player's numbers so far (for in-game props)."""
    live = [g for g in games if g["state"] == "in" and g["sport"] in PATH]
    def one(g):
        try:
            path = PATH[g["sport"]] or f"soccer/{g['league']}"
            s = espn.get(path + "/summary", ttl=0, pace=False, event=g["id"])
            g["players"] = box_stats(g["sport"], s, g)
        except Exception as e:                           # one game failing must not hide the others
            print(f"  box score {g['home']} v {g['away']}: skipped ({e})")
            g["players"] = {}
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(one, live))
    for g in live:
        g["f"] = round(elapsed_fraction(g["sport"], g.get("period", 0), g.get("clock", ""), g.get("clock", "")), 3)
    for g in games:
        if g["state"] == "post" and "players" not in g:
            pass


def main(until: str | None = None):
    jobs = [("nba", "nba", "NBA", "basketball/nba"), ("nfl", "nfl", "NFL", "football/nfl"), ("cfb", "cfb", "College football", "football/college-football", {"groups": 80})] + [("football", k, v, f"soccer/{k}") for k, v in LEAGUES.items()]
    with ThreadPoolExecutor(11) as pool:
        rows = [r for part in pool.map(fetch_one, jobs) for r in part]
    seen, uniq = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"]); uniq.append(r)
    now = dt.datetime.now(dt.timezone.utc)
    # keep: in play, finished within the last day, or starting in the next day
    keep = []
    for r in uniq:
        start = dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00"))
        if r["state"] == "in" or (r["state"] == "post" and now - start < dt.timedelta(hours=30)) or (r["state"] == "pre" and start - now < dt.timedelta(hours=30)):
            keep.append(r)
    keep.sort(key=lambda r: (r["state"] != "in", r["start"]))
    add_box_scores(keep)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = {"generated_at": now.isoformat(timespec="seconds"), "games": keep}
    if until:   # live tracking: the page shows "tracking on" until this time
        doc["tracking_until"] = now.isoformat(timespec="seconds") if until == "now" else until
    OUT.write_text(json.dumps(doc, separators=(",", ":")))
    active = sum(r["state"] == "in" or (r["state"] == "pre" and dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")) - now < dt.timedelta(minutes=30)) for r in keep)
    print(f"wrote {OUT}: {sum(r['state']=='in' for r in keep)} live, {sum(r['state']=='post' for r in keep)} finished, {sum(r['state']=='pre' for r in keep)} upcoming")
    print(f"ACTIVE={active}")


# ---------- live box scores (for in-game props) ----------
PATH = {"nba": "basketball/nba", "nfl": "football/nfl", "cfb": "football/college-football", "football": None}


def norm(s: str) -> str:
    """Same name clean-up the page uses to match ESPN names to the prediction files."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = "".join(c for c in s if c.isalnum() or c == " ")
    return re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", s.strip())


def elapsed_fraction(sport: str, period: int, clock: str, display: str = "") -> float:
    """Share of the game already played, 0..1. Basketball 4 x 12 min, American football 4 x 15 min, football 90 min."""
    def mmss(c):
        m = re.match(r"^(\d+):(\d+)", c or "")
        return int(m.group(1)) + int(m.group(2)) / 60 if m else None
    if sport in ("nba", "nfl", "cfb"):
        q, n = (12, 4) if sport == "nba" else (15, 4)
        left = mmss(clock)
        if left is None:
            return min(period, n) / n
        if period > n:
            return 1.0 - 0.01                          # overtime: nearly over by the regular clock
        return min(0.995, ((period - 1) * q + (q - left)) / (q * n))
    m = re.match(r"^(\d+)", display or "")
    return min(0.995, int(m.group(1)) / 90) if m else 0.0


def box_stats(sport: str, summary: dict, game: dict) -> dict:
    """name -> {stat: value so far} using the stat keys the prediction files use."""
    out = {}
    if sport == "nba":
        for tm in summary.get("boxscore", {}).get("players", []):
            for cat in tm.get("statistics", []):
                keys = cat.get("keys", [])
                for a in cat.get("athletes", []):
                    st = dict(zip(keys, a.get("stats", [])))
                    if not st:
                        continue
                    def num(k):
                        try:
                            return int(float(str(st.get(k, 0)).split("-")[0]))
                        except ValueError:
                            return 0
                    out[norm(a["athlete"]["displayName"])] = {"pts": num("points"), "reb": num("rebounds"), "ast": num("assists"),
                                                              "fg3": num("threePointFieldGoalsMade-threePointFieldGoalsAttempted"), "min": num("minutes")}
    elif sport in ("nfl", "cfb"):
        from .us_ingest import parse_players
        g = {"game_id": game["id"], "league": sport, "date": "", "home_id": game["home_id"]}
        for r in parse_players(summary, g):
            out[norm(r["player"])] = {s: r[s] for s in ("pass_yds", "pass_td", "rush_yds", "rec_yds", "rec")}
    else:
        from .soccer_ingest import parse_players
        m = {"match_id": game["id"], "league": "", "date": "", "home_id": game["home_id"], "away_id": game["away_id"], "home": game["home"], "away": game["away"]}
        for r in parse_players(summary, m):
            out[norm(r["player"])] = {s: r[s] for s in ("shots", "sot", "goals", "assists")}
    return out



if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="ISO time live tracking runs until, or 'now' to switch it off")
    main(ap.parse_args().until)
