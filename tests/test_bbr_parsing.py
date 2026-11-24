"""Sanity checks on downloaded data. Uses the cached page of the first game of 2026-27."""
import pytest

from betsuggester import bbr

GAME = "202610200DET"
CACHE = bbr.CACHE_DIR / f"boxscores__{GAME}.html"


@pytest.mark.skipif(not CACHE.exists(), reason="run the ingest first")
def test_boxscore_players_add_up_to_team_score():
    rows = bbr.parse_boxscore(CACHE.read_text(encoding="utf-8"), GAME)
    sched = bbr.fetch("/leagues/NBA_2027_games-october.html")
    game = next(g for g in bbr.parse_schedule(sched) if g["game_id"] == GAME)
    pts = {}
    for r in rows:
        pts[r["team"]] = pts.get(r["team"], 0) + r["pts"]
    assert sorted(pts.values()) == sorted([game["home_pts"], game["away_pts"]])
    assert all(r["minutes"] > 0 for r in rows)
    assert {r["is_home"] for r in rows} == {0, 1}
