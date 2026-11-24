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
    return df.sort_values(["date", "game_id"]).reset_index(drop=True)


FEATURES = ["stat_avg5", "stat_avg10", "min_avg5", "min_avg10", "stat_std10", "stat_career_avg",
            "games_prior", "rest_days", "per_min10", "opp_allowed15", "is_home"]
