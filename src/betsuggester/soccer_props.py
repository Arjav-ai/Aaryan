"""Football player props: shots, shots on target, goals, assists (given the player plays)."""
import sys

import numpy as np
import pandas as pd

from .db import connect
from .model import fit_calibrated

STATS = ["shots", "sot", "goals", "assists"]
LABELS = {"shots": "Shots", "sot": "Shots on target", "goals": "Goals", "assists": "Assists"}
LINES = {"shots": [0.5, 1.5, 2.5], "sot": [0.5, 1.5], "goals": [0.5], "assists": [0.5]}
FEATURES = ["stat_avg5", "stat_avg10", "stat_career_avg", "games_prior", "start_rate5", "start_rate10", "pos_code",
            "is_home", "team_gf10", "opp_ga10", "opp_allowed15", "rest_days"]


def pos_code(a):
    """0 keeper, 1 defender, 2 midfielder, 3 forward (None when unknown / substitute)."""
    if not isinstance(a, str) or a.upper() == "SUB":
        return np.nan
    a = a.upper()
    if a == "G": return 0
    if a.startswith("DM"): return 2
    if a.startswith(("CD", "LB", "RB", "LWB", "RWB", "SW", "D")): return 1
    if a.startswith(("CM", "AM", "LM", "RM", "M")): return 2
    if a.startswith(("F", "CF", "LF", "RF", "ST", "S")): return 3
    return 2


def load_player_games() -> pd.DataFrame:
    df = pd.read_sql_query("""SELECT p.*, m.home_id, m.away_id, m.home_goals, m.away_goals
                              FROM soccer_player_games p JOIN soccer_matches m USING (match_id) ORDER BY p.date, p.match_id""", connect())
    df["date"] = pd.to_datetime(df["date"])
    df["opp_id"] = np.where(df.is_home == 1, df.away_id, df.home_id)
    df["team_goals"] = np.where(df.is_home == 1, df.home_goals, df.away_goals)
    df["opp_goals"] = np.where(df.is_home == 1, df.away_goals, df.home_goals)
    df["pos_c"] = df["pos"].map(pos_code)
    return df


def add_features(df: pd.DataFrame, stat: str) -> pd.DataFrame:
    """Only information known before kick-off goes into a row's features."""
    df = df.sort_values(["date", "match_id"]).copy()
    g = df.groupby("player_id")
    roll = lambda col, n: g[col].transform(lambda s: s.shift(1).rolling(n, min_periods=3).mean())
    df["stat_avg5"], df["stat_avg10"] = roll(stat, 5), roll(stat, 10)
    df["stat_career_avg"] = g[stat].transform(lambda s: s.shift(1).expanding().mean())
    df["start_rate5"], df["start_rate10"] = roll("starter", 5), roll("starter", 10)
    df["games_prior"] = g.cumcount()
    df["rest_days"] = g["date"].transform(lambda s: s.diff().dt.days).clip(upper=14)
    last_pos = g["pos_c"].transform(lambda s: s.shift(1).ffill())
    df["pos_code"] = last_pos.fillna(df["pos_c"]).fillna(2)

    tm = df.drop_duplicates(["team_id", "match_id"])[["team_id", "match_id", "date", "team_goals", "opp_goals"]].sort_values("date")
    tg = tm.groupby("team_id")
    tm["gf10"] = tg["team_goals"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    tm["ga10"] = tg["opp_goals"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    df = df.merge(tm[["team_id", "match_id", "gf10"]].rename(columns={"gf10": "team_gf10"}), on=["team_id", "match_id"], how="left")
    df = df.merge(tm[["team_id", "match_id", "ga10"]].rename(columns={"team_id": "opp_id", "ga10": "opp_ga10"}), on=["opp_id", "match_id"], how="left")
    # what the opponent has been allowing of this stat (per match, whole team)
    allowed = df.groupby(["opp_id", "match_id", "date"], as_index=False)[stat].sum(min_count=1).sort_values("date")
    allowed["opp_allowed15"] = allowed.groupby("opp_id")[stat].transform(lambda s: s.shift(1).rolling(15, min_periods=5).mean())
    df = df.merge(allowed[["opp_id", "match_id", "opp_allowed15"]], on=["opp_id", "match_id"], how="left")
    return df.sort_values(["date", "match_id"]).reset_index(drop=True)


# Opponent / team context may be missing for clubs with little data (e.g. Champions League newcomers).
# The model handles a missing value, so we don't drop those rows.
REQUIRED = [f for f in FEATURES if f not in ("team_gf10", "opp_ga10", "opp_allowed15")]


def prepare(stat):
    df = add_features(load_player_games(), stat).dropna(subset=REQUIRED)
    return df[(df.games_prior >= 5) & (df.pos_code > 0) & (df.start_rate10 >= 0.5)]   # outfield regulars


def backtest(split, stat, df=None, quiet=False):
    df = prepare(stat) if df is None else df
    train, test = df[df.date < split], df[df.date >= split]
    m = fit_calibrated(train, stat, FEATURES, LINES[stat])
    mu, y, base = m.mean(test), test[stat].to_numpy(), test["stat_avg10"].to_numpy()
    rows, ll, ln = [], [], []
    for line in LINES[stat]:
        hit = y > line
        p, pn = (np.clip(m.p_over(x, np.full(len(y), line)), 1e-4, 1 - 1e-4) for x in (mu, base))
        ll.append(-np.mean(hit * np.log(p) + ~hit * np.log(1 - p))); ln.append(-np.mean(hit * np.log(pn) + ~hit * np.log(1 - pn)))
        rows.append(pd.DataFrame({"p": p, "hit": hit.astype(int)}))
    if not quiet:
        print(f"{stat}: train {len(train)}, test {len(test)} | MAE model {np.mean(np.abs(mu-y)):.3f} vs last-10 avg {np.mean(np.abs(base-y)):.3f} | "
              f"log-loss model {np.mean(ll):.4f} vs naive {np.mean(ln):.4f}")
        r = pd.concat(rows); r["b"] = pd.cut(r.p, [0, .1, .2, .3, .4, .5, .6, .8, 1.0])
        print(r.groupby("b", observed=True).agg(n=("hit", "size"), said=("p", "mean"), actual=("hit", "mean")).round(3).to_string())
    return m


if __name__ == "__main__":
    for st in STATS:
        backtest(sys.argv[1] if len(sys.argv) > 1 else "2026-02-01", st)
