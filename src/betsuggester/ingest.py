"""Download NBA games + player box scores into the local database.

Usage:  python -m betsuggester.ingest 2027        (2027 = the 2026-27 season)
Safe to re-run: finished games are skipped, so it only fetches what's new.
"""
import sys

from . import bbr
from .db import connect


def ingest_season(season: int) -> None:
    conn = connect()
    have = {r[0] for r in conn.execute("SELECT game_id FROM games")}
    new_games = 0
    for path in bbr.season_months(season):
        html = bbr.fetch(path)
        if html is None:
            continue  # month not in this season (or not played yet)
        for g in bbr.parse_schedule(html):
            if g["game_id"] in have:
                continue
            box = bbr.fetch(g["path"])
            rows = bbr.parse_boxscore(box, g["game_id"])
            with conn:
                conn.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?)", (
                    g["game_id"], g["date"], season, g["away_team"], g["home_team"],
                    g["away_pts"], g["home_pts"]))
                conn.executemany(
                    "INSERT OR REPLACE INTO player_games VALUES "
                    "(:game_id,:team,:is_home,:player,:minutes,:pts,:reb,:ast,:fg3,:stl,:blk,:tov)", rows)
            new_games += 1
            print(f"{g['date']} {g['away_team']} @ {g['home_team']}: {len(rows)} players", flush=True)
    print(f"Season {season}: {new_games} new games saved.")


if __name__ == "__main__":
    for s in sys.argv[1:] or ["2027"]:
        ingest_season(int(s))
