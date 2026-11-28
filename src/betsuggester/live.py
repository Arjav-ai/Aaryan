"""Live scores for today's NBA games and football matches -> data/live.json (takes a few seconds).

Usage: python -m betsuggester.live
Only today's scoreboards (UTC today and yesterday, so late games are not lost). No database, no model.
"""
import datetime as dt
import argparse
import json
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
    sport, league, name, path = args
    out = []
    today = dt.datetime.now(dt.timezone.utc).date()
    for d in (today - dt.timedelta(days=1), today):
        try:
            sb = espn.get(path + "/scoreboard", ttl=0, pace=False, dates=d.strftime("%Y%m%d"))
        except Exception as e:      # one league failing must not hide the others
            print(f"{name}: skipped ({e})")
            continue
        out += [r for r in (parse(ev, sport, league, name) for ev in sb.get("events", [])) if r]
    return out


def main(until: str | None = None):
    jobs = [("nba", "nba", "NBA", "basketball/nba")] + [("football", k, v, f"soccer/{k}") for k, v in LEAGUES.items()]
    with ThreadPoolExecutor(9) as pool:
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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = {"generated_at": now.isoformat(timespec="seconds"), "games": keep}
    if until:   # live tracking: the page shows "tracking on" until this time
        doc["tracking_until"] = now.isoformat(timespec="seconds") if until == "now" else until
    OUT.write_text(json.dumps(doc, separators=(",", ":")))
    active = sum(r["state"] == "in" or (r["state"] == "pre" and dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")) - now < dt.timedelta(minutes=30)) for r in keep)
    print(f"wrote {OUT}: {sum(r['state']=='in' for r in keep)} live, {sum(r['state']=='post' for r in keep)} finished, {sum(r['state']=='pre' for r in keep)} upcoming")
    print(f"ACTIVE={active}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="ISO time live tracking runs until, or 'now' to switch it off")
    main(ap.parse_args().until)
