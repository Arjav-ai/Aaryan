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
CREATE TABLE IF NOT EXISTS nba_lines (
  game_id TEXT PRIMARY KEY, espn_id TEXT, provider TEXT, spread REAL, total REAL, home_ml REAL, away_ml REAL);
CREATE TABLE IF NOT EXISTS soccer_matches (
  match_id TEXT PRIMARY KEY, league TEXT, season INTEGER, date TEXT,
  home_id TEXT, home TEXT, away_id TEXT, away TEXT, home_goals INTEGER, away_goals INTEGER);
CREATE TABLE IF NOT EXISTS soccer_player_games (
  match_id TEXT, league TEXT, date TEXT, team_id TEXT, team TEXT, is_home INTEGER,
  player_id TEXT, player TEXT, pos TEXT, starter INTEGER, sub_in INTEGER, sub_out INTEGER,
  shots INTEGER, sot INTEGER, goals INTEGER, assists INTEGER, fouls INTEGER, fouled INTEGER,
  yellow INTEGER, saves INTEGER, PRIMARY KEY (match_id, player_id));
CREATE TABLE IF NOT EXISTS us_games (
  game_id TEXT PRIMARY KEY, league TEXT, season INTEGER, week INTEGER, date TEXT,
  home_id TEXT, home TEXT, home_abbr TEXT, away_id TEXT, away TEXT, away_abbr TEXT,
  home_pts INTEGER, away_pts INTEGER, neutral INTEGER, spread REAL, total REAL);
CREATE TABLE IF NOT EXISTS us_player_games (
  game_id TEXT, league TEXT, date TEXT, team_id TEXT, team TEXT, is_home INTEGER,
  player_id TEXT, player TEXT, pass_att INTEGER, pass_yds INTEGER, pass_td INTEGER, pass_int INTEGER,
  rush_att INTEGER, rush_yds INTEGER, rush_td INTEGER, rec INTEGER, rec_yds INTEGER, rec_td INTEGER, targets INTEGER,
  PRIMARY KEY (game_id, player_id));
CREATE TABLE IF NOT EXISTS tennis_matches (
  match_id TEXT PRIMARY KEY, tour TEXT, date TEXT, tournament TEXT, major INTEGER, best_of INTEGER,
  p1_id TEXT, p1 TEXT, p1_rank INTEGER, p2_id TEXT, p2 TEXT, p2_rank INTEGER,
  winner INTEGER, sets TEXT, status TEXT, state TEXT, games1 INTEGER, games2 INTEGER, sets1 INTEGER, sets2 INTEGER);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.executescript(SCHEMA)
    return conn
