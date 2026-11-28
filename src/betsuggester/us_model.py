"""American football (NFL and college) player-prop and game models.

Player props: a player's expected number for a stat is a recency-weighted average of the games where he had that
role (attempts / carries / targets), pulled toward the league-wide average for that role when there are few games,
and scaled by how much the opposing defence allows against that kind of play. Spread of outcomes: negative binomial
with a dispersion tuned by walk-forward testing (us_backtest.py).

Games: reuses the team-rating (ridge) score model written for the NBA, with home field and no back-to-back term.
"""
import numpy as np
import pandas as pd
from scipy import stats

from .db import connect
from .nba_game_model import GameModel

STATS = {"pass_yds": "Passing yards", "pass_td": "Passing TDs", "rush_yds": "Rushing yards", "rec_yds": "Receiving yards", "rec": "Receptions"}
STAT_ORDER = list(STATS)
# role column and the minimum usage in a game for it to count as "he had that role"
ROLE_CFB = {"rec_yds": ("rec", 2), "rec": ("rec", 2)}      # college box scores have no "targets" column
ROLE = {"pass_yds": ("pass_att", 8), "pass_td": ("pass_att", 8), "rush_yds": ("rush_att", 4), "rec_yds": ("targets", 2), "rec": ("targets", 2)}
# which team-level total of the OPPOSING side measures how generous the defence is for this stat
ALLOWED = {"pass_yds": "pass_yds", "pass_td": "pass_td", "rush_yds": "rush_yds", "rec_yds": "pass_yds", "rec": "pass_yds"}
# tuned in us_backtest.py
DEFAULTS = {"half": 0.8, "recent": 8, "prior_n": 2.0, "opp_k": 4.0, "opp_pow": 0.5}
# dispersion per stat, fitted in us_backtest.py (walk-forward, NFL 2026 weeks 5+ and college 2026 weeks 5+)
ALPHA = {"nfl": {"pass_yds": 0.12, "pass_td": 0.05, "rush_yds": 0.38, "rec_yds": 0.69, "rec": 0.05},
         "cfb": {"pass_yds": 0.19, "pass_td": 0.05, "rush_yds": 0.69, "rec_yds": 0.43, "rec": 0.05}}
SD_MARGIN = {"nfl": 12.8, "cfb": 16.5}     # measured residual spread (12.3 / 15.8), widened a little for overconfidence at 55-70%
SD_TOTAL = {"nfl": 13.8, "cfb": 16.7}
# team-rating settings tuned in us_backtest.py (ridge strength, half-life of old games in days)
GAME_FIT = {"nfl": {"ridge": 2.0, "half_life": 240}, "cfb": {"ridge": 0.5, "half_life": 120}}


def load(league: str):
    conn = connect()
    g = pd.read_sql_query("SELECT * FROM us_games WHERE league=? ORDER BY date, game_id", conn, params=(league,))
    p = pd.read_sql_query("SELECT * FROM us_player_games WHERE league=? ORDER BY date, game_id", conn, params=(league,))
    g["date"] = pd.to_datetime(g["date"]); p["date"] = pd.to_datetime(p["date"])
    return g, p


class Projector:
    """Holds the history once; project() answers 'what do we expect from this player, against this team, on this date'."""

    def __init__(self, games: pd.DataFrame, players: pd.DataFrame, league: str = "nfl", **kw):
        self.k = {**DEFAULTS, **kw}
        self.role = {**ROLE, **(ROLE_CFB if league == "cfb" else {})}
        self.games = games
        # opponent-allowed totals per (team, game): what the team's defence conceded in each category
        tot = players.groupby(["game_id", "team_id"])[["pass_yds", "pass_td", "rush_yds"]].sum().reset_index()
        meta = games[["game_id", "date", "home_id", "away_id"]]
        tot = tot.merge(meta, on="game_id")
        tot["def_team"] = np.where(tot.team_id == tot.home_id, tot.away_id, tot.home_id)   # the side that conceded these numbers
        self.conceded = {tid: d.sort_values("date") for tid, d in tot.groupby("def_team")}
        self.team_dates = {}
        for r in games.itertuples(index=False):
            for t in (r.home_id, r.away_id):
                self.team_dates.setdefault(t, []).append(r.date)
        self.series = {}
        for stat, (rc, thr) in self.role.items():
            use = players[players[rc] >= thr]
            self.series[stat] = {pid: d.sort_values("date")[["date", stat, "team_id"]].to_numpy() for pid, d in use.groupby("player_id")}
        self.lg = {stat: float(players.loc[players[self.role[stat][0]] >= self.role[stat][1], stat].mean()) for stat in STATS}
        self.lg_allowed = {c: float(tot[c].mean()) for c in ("pass_yds", "pass_td", "rush_yds")}

    def opp_factor(self, stat, opp_id, date):
        c = ALLOWED[stat]; d = self.conceded.get(opp_id)
        if d is None:
            return 1.0
        d = d[d.date < date]
        if d.empty:
            return 1.0
        n, ratio = len(d), float(d[c].mean()) / max(self.lg_allowed[c], 1e-9)
        f = (n * ratio + self.k["opp_k"]) / (n + self.k["opp_k"])
        return f ** self.k["opp_pow"]

    def project(self, player_id, stat, team_id, opp_id, date):
        """-> (mu, n_games) or None when he has not played that role enough recently."""
        arr = self.series[stat].get(player_id)
        if arr is None:
            return None
        arr = arr[arr[:, 0] < date]
        if len(arr) < 2:
            return None
        last = arr[-self.k["recent"]:]
        # must have had the role in at least half of the team's last six games (otherwise he is a part-timer or hurt)
        td = [d for d in self.team_dates.get(team_id, []) if d < date][-6:]
        if not td or (last[:, 0] >= td[0]).sum() / len(td) < 0.5:
            return None
        w = self.k["half"] ** np.arange(len(last))[::-1]
        base = float((last[:, 1].astype(float) * w).sum() / w.sum())
        n = len(last)
        mu = (n * base + self.k["prior_n"] * self.lg[stat]) / (n + self.k["prior_n"])
        return mu * self.opp_factor(stat, opp_id, date), n


def nb_pmf_over(mu, alpha, line):
    """P(X > line) for a negative binomial with mean mu and variance mu + alpha*mu^2."""
    r = 1.0 / alpha; p = r / (r + mu)
    return float(stats.nbinom.sf(np.floor(line), r, p))


def nb_loglik(y, mu, alpha):
    r = 1.0 / alpha
    return stats.nbinom.logpmf(y, r, r / (r + np.asarray(mu)))


# ---------- games ----------
def game_frame(g: pd.DataFrame) -> pd.DataFrame:
    d = g.drop(columns=["home", "away"]).rename(columns={"home_id": "home", "away_id": "away"}).copy()
    d["home_b2b"] = 0; d["away_b2b"] = 0
    return d


def fit_games(g: pd.DataFrame, asof, ridge=5.0, half_life=120):
    return GameModel(half_life_days=half_life, alpha=ridge, use_rest=False, level_days=0).fit(game_frame(g), asof)
