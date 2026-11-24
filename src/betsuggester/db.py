import sqlite3
from pathlib import Path

DB_PATH = Path("data/nba.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY, date TEXT, season INTEGER,
  away_team TEXT, home_team TEXT, away_pts INTEGER, home_pts INTEGER);
CREATE TABLE IF NOT EXISTS player_games (
  game_id TEXT, team TEXT, is_home INTEGER, player TEXT, minutes REAL,
  pts INTEGER, reb INTEGER, ast INTEGER, fg3 INTEGER, stl INTEGER, blk INTEGER, tov INTEGER,
  PRIMARY KEY (game_id, player));
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn
