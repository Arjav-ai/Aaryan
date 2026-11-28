"""Download club crests (96x96 PNG) for every team that appears in the football predictions.

Usage: python -m betsuggester.crests        -> writes site/crests/<espn team id>.png (skips ones we already have)
The page shows a plain initials badge for any club whose crest is missing, so a failed download is harmless.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

OUT = Path("site/crests")
URL = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/soccer/500/{id}.png&w=96&h=96"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal research project)"}


def team_ids(predictions="data/predictions_soccer.json") -> set[str]:
    d = json.loads(Path(predictions).read_text())
    ids = set()
    for g in d["games"]:
        ids |= {g["home_id"], g["away_id"]}
    for o in d["outrights"].values():
        ids |= {t["team_id"] for t in o["teams"]}
    return ids


def fetch(team_id: str) -> str:
    f = OUT / f"{team_id}.png"
    if f.exists() and f.stat().st_size > 200:
        return "have"
    try:
        r = requests.get(URL.format(id=team_id), headers=HEADERS, timeout=30)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 200:
            f.write_bytes(r.content)
            return "new"
        return f"missing ({r.status_code})"
    except requests.RequestException as e:
        return f"failed ({type(e).__name__})"


# ESPN's NBA abbreviations -> the codes our NBA data uses (Basketball-Reference)
NBA_CODES = {"BKN": "BRK", "CHA": "CHO", "GS": "GSW", "NO": "NOP", "NY": "NYK", "PHX": "PHO", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}


def fetch_nba() -> str:
    """The 30 NBA team logos -> site/crests/nba/<code>.png"""
    from . import espn
    out = OUT / "nba"
    out.mkdir(parents=True, exist_ok=True)
    teams = espn.get("basketball/nba/teams")["sports"][0]["leagues"][0]["teams"]
    got = 0
    for t in teams:
        t = t["team"]; code = NBA_CODES.get(t["abbreviation"], t["abbreviation"]); f = out / f"{code}.png"
        if f.exists() and f.stat().st_size > 200:
            got += 1; continue
        path = t["logos"][0]["href"].replace("https://a.espncdn.com", "")
        r = requests.get(f"https://a.espncdn.com/combiner/i?img={path}&w=96&h=96", headers=HEADERS, timeout=30)
        if r.status_code == 200 and len(r.content) > 200:
            f.write_bytes(r.content); got += 1
    return f"{got} of {len(teams)} NBA logos"


def fetch_us(league: str, path: str, extra: dict) -> str:
    """Logos for NFL / college football teams that appear in the predictions -> site/crests/<league>/<espn team id>.png"""
    from . import espn
    f = Path(f"data/predictions_{league}.json")
    if not f.exists():
        return "no predictions yet"
    d = json.loads(f.read_text())
    need = {g[k] for g in d["games"] for k in ("home_id", "away_id")}
    out = OUT / league
    out.mkdir(parents=True, exist_ok=True)
    teams = espn.get(path + "/teams", ttl=86400, limit=500, **extra)["sports"][0]["leagues"][0]["teams"]
    got = 0
    for t in teams:
        t = t["team"]
        if t["id"] not in need:
            continue
        dest = out / f"{t['id']}.png"
        if dest.exists() and dest.stat().st_size > 200:
            got += 1; continue
        if not t.get("logos"):
            continue
        img = t["logos"][0]["href"].replace("https://a.espncdn.com", "")
        r = requests.get(f"https://a.espncdn.com/combiner/i?img={img}&w=96&h=96", headers=HEADERS, timeout=30)
        if r.status_code == 200 and len(r.content) > 200:
            dest.write_bytes(r.content); got += 1
    return f"{got} of {len(need)} logos"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("NBA:", fetch_nba())
    for lg, path, extra in (("nfl", "football/nfl", {}), ("cfb", "football/college-football", {"groups": 80})):
        try:
            print(lg.upper() + ":", fetch_us(lg, path, extra))
        except Exception as e:
            print(lg.upper() + ": skipped", e)
    ids = sorted(team_ids())
    with ThreadPoolExecutor(4) as pool:
        results = dict(zip(ids, pool.map(fetch, ids)))
    new = sum(r == "new" for r in results.values())
    bad = {k: v for k, v in results.items() if v not in ("new", "have")}
    size = sum(f.stat().st_size for f in OUT.glob("*.png"))
    print(f"{len(ids)} clubs: {new} downloaded, {len(ids) - new - len(bad)} already had, {len(bad)} without a crest; folder {size // 1024} KB")
    for k, v in bad.items():
        print("  no crest for team", k, v)


if __name__ == "__main__":
    main()
