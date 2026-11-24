"""Download and parse NBA data from Basketball-Reference.

Politeness matters: the site blocks clients that make more than ~20 requests
a minute, so every request waits MIN_DELAY seconds and every page is cached
on disk so it is never downloaded twice.
"""
import io
import re
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.basketball-reference.com"
MIN_DELAY = 3.5
CACHE_DIR = Path("data/cache")
HEADERS = {"User-Agent": "Mozilla/5.0 (personal research project)"}
MONTHS = ["october", "november", "december", "january", "february", "march", "april", "may", "june"]

_last_request = 0.0


def fetch(path: str) -> str | None:
    """Return the page HTML (from cache if we have it). None if the page doesn't exist."""
    global _last_request
    cache_file = CACHE_DIR / (path.strip("/").replace("/", "__") or "index")
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    wait = MIN_DELAY - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(BASE + path, headers=HEADERS, timeout=40)
    _last_request = time.time()
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RuntimeError("Rate-limited by Basketball-Reference; wait a few minutes and re-run.")
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


def season_months(season_end_year: int, today_month_names=MONTHS) -> list[str]:
    """Schedule page paths for a season (e.g. 2027 = the 2026-27 season)."""
    return [f"/leagues/NBA_{season_end_year}_games-{m}.html" for m in today_month_names]


def parse_schedule(html: str) -> list[dict]:
    """Finished games on a schedule page: box score path, date, teams, scores."""
    table = pd.read_html(io.StringIO(html))[0]
    links = re.findall(r'href="(/boxscores/\d{8}0[A-Z]{3}\.html)"', html)
    played = table[table["PTS"].notna() & (table["Date"] != "Date")]
    if len(played) != len(links):
        raise ValueError(f"schedule mismatch: {len(played)} games but {len(links)} box score links")
    games = []
    for (_, row), link in zip(played.iterrows(), links):
        games.append({
            "game_id": link.split("/")[-1].removesuffix(".html"),
            "path": link,
            "date": pd.to_datetime(row["Date"]).date().isoformat(),
            "away_team": row["Visitor/Neutral"],
            "home_team": row["Home/Neutral"],
            "away_pts": int(row["PTS"]),
            "home_pts": int(row["PTS.1"]),
        })
    return games


def _minutes(value) -> float | None:
    if isinstance(value, str) and ":" in value:
        m, s = value.split(":")
        return int(m) + int(s) / 60
    return None


def parse_boxscore(html: str, game_id: str) -> list[dict]:
    """One row per player who actually played, for both teams."""
    home_code = game_id[-3:]
    rows = []
    for code in re.findall(r'id="box-([A-Z]{3})-game-basic"', html):
        table = pd.read_html(io.StringIO(html), attrs={"id": f"box-{code}-game-basic"})[0]
        table.columns = [c[1] if isinstance(c, tuple) else c for c in table.columns]
        table = table.rename(columns={table.columns[0]: "player"})
        for _, r in table.iterrows():
            minutes = _minutes(r.get("MP"))
            if minutes is None or r["player"] in ("Reserves", "Team Totals"):
                continue  # header rows, totals, did-not-play
            rows.append({
                "game_id": game_id,
                "team": code,
                "is_home": int(code == home_code),
                "player": r["player"],
                "minutes": minutes,
                "pts": int(r["PTS"]), "reb": int(r["TRB"]), "ast": int(r["AST"]),
                "fg3": int(r["3P"]), "stl": int(r["STL"]), "blk": int(r["BLK"]), "tov": int(r["TOV"]),
            })
    return rows
