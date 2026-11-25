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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
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
