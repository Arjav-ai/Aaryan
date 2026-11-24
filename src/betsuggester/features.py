"""Build one row per player-game using ONLY information known before tip-off."""
import pandas as pd

from .db import connect


def load_player_games() -> pd.DataFrame:
    conn = connect()
    df = pd.read_sql_query(
        """SELECT p.*, g.date, g.season, g.home_team, g.away_team
           FROM player_games p JOIN games g USING (game_id) ORDER BY g.date, p.game_id""", conn)
    df["date"] = pd.to_datetime(df["date"])
    df["opp"] = df.apply(lambda r: r.away_team if r.is_home else r.home_team, axis=1)
    return df


def add_features(df: pd.DataFrame, stat: str = "pts") -> pd.DataFrame:
    df = df.sort_values(["player", "date", "game_id"]).copy()
    g = df.groupby("player", group_keys=False)

    def roll(col, n):  # average of the previous n games (never includes today's game)
        return g[col].transform(lambda s: s.shift(1).rolling(n, min_periods=3).mean())

    df["stat_avg5"], df["stat_avg10"] = roll(stat, 5), roll(stat, 10)
    df["min_avg5"], df["min_avg10"] = roll("minutes", 5), roll("minutes", 10)
    df["stat_std10"] = g[stat].transform(lambda s: s.shift(1).rolling(10, min_periods=5).std())
    df["stat_career_avg"] = g[stat].transform(lambda s: s.shift(1).expanding().mean())
    df["games_prior"] = g.cumcount()
    df["rest_days"] = g["date"].transform(lambda s: s.diff().dt.days).clip(upper=7)
    df["per_min10"] = df["stat_avg10"] / df["min_avg10"].clip(lower=1)

    # How much does the opponent allow? Average of what opposing players scored vs them, last 15 games.
    team_game = df.groupby(["opp", "date", "game_id"], as_index=False)[stat].sum().sort_values("date")
    team_game["opp_allowed15"] = team_game.groupby("opp")[stat].transform(
        lambda s: s.shift(1).rolling(15, min_periods=5).mean())
    df = df.merge(team_game[["opp", "game_id", "opp_allowed15"]], on=["opp", "game_id"], how="left")
    df = add_absence_features(df, stat)
    return df.sort_values(["date", "game_id"]).reset_index(drop=True)


ROTATION_MINUTES = 15   # a teammate averaging this many minutes counts as "rotation"
ABSENCE_WINDOW = 10     # only look at teammates who played in the team's last N games


def rotation_snapshot(history_rows):
    """history_rows: iterable of (player, min_post10, stat_post10) from a team's last N games, oldest first.
    Returns {player: (min10, stat10)} for rotation players (latest values win)."""
    latest = {}
    for player, mn, st in history_rows:
        latest[player] = (mn, st)
    return {p: v for p, v in latest.items() if v[0] >= ROTATION_MINUTES}


def absence_numbers(rotation, missing_players):
    """Total minutes / production of rotation players who will not play."""
    out = [rotation[p] for p in missing_players if p in rotation]
    return {"out_min": sum(m for m, _ in out), "out_stat": sum(s for _, s in out), "n_out": len(out)}


def add_absence_features(df: pd.DataFrame, stat: str) -> pd.DataFrame:
    """For every team-game: which regular rotation players (from the last 10 team games) did NOT play?"""
    df = df.sort_values(["date", "game_id"]).copy()
    g = df.groupby("player")
    df["min_post10"] = g["minutes"].transform(lambda s: s.rolling(10, min_periods=3).mean())
    df["stat_post10"] = g[stat].transform(lambda s: s.rolling(10, min_periods=3).mean())
    rows = []
    for team, tdf in df.groupby("team"):
        by_game = {gid: grp for gid, grp in tdf.groupby("game_id", sort=False)}
        games = list(by_game)  # chronological: df is sorted by date
        for i, gid in enumerate(games):
            history = [t for gj in games[max(0, i - ABSENCE_WINDOW):i]
                       for t in by_game[gj][["player", "min_post10", "stat_post10"]].itertuples(index=False, name=None)]
            rotation = rotation_snapshot(history)
            missing = set(rotation) - set(by_game[gid].player)
            rows.append({"team": team, "game_id": gid, **absence_numbers(rotation, missing)})
    return df.merge(pd.DataFrame(rows), on=["team", "game_id"], how="left")


FEATURES = ["stat_avg5", "stat_avg10", "min_avg5", "min_avg10", "stat_std10", "stat_career_avg",
            "games_prior", "rest_days", "per_min10", "opp_allowed15", "is_home"]
# Absence numbers (out_min, out_stat, n_out) are computed but NOT used as model inputs: A/B tested over
# 13,943 player-games and they did not improve accuracy with one season of history. The app shows them as a warning.
