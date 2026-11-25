"""NBA game model: predicts each team's score from attack / defence ratings, home court and back-to-backs.
From the two expected scores we get the expected margin and total, and (with a spread of uncertainty) the
chance of every moneyline, spread and total-points bet.
"""
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge

from .db import connect

Q = """SELECT g.game_id, g.date, g.season, g.home_pts, g.away_pts, hp.team AS home, ap.team AS away
       FROM games g JOIN (SELECT DISTINCT game_id, team FROM player_games WHERE is_home = 1) hp USING (game_id)
                    JOIN (SELECT DISTINCT game_id, team FROM player_games WHERE is_home = 0) ap USING (game_id)
       ORDER BY g.date, g.game_id"""

# Spread of the actual result around the model's expectation (points). Tuned in nba_game_backtest.
SD_MARGIN, SD_TOTAL = 15.0, 19.0


def load_games(regular_season_only: bool = True) -> pd.DataFrame:
    """All games with scores. Playoff games are dropped by default: they are much lower-scoring (216 vs 231 points
    per game last season) and a regular-season betting page should not learn from them."""
    df = pd.read_sql_query(Q, connect())
    df["date"] = pd.to_datetime(df["date"])
    if regular_season_only:
        keep = []
        for _, s in df.groupby("season"):
            s = s.sort_values(["date", "game_id"])
            keep.extend(s.index[:1230])       # a full regular season is 1,230 games
        df = df.loc[sorted(keep)]
    return df.reset_index(drop=True)


def add_rest(df: pd.DataFrame) -> pd.DataFrame:
    """Back-to-back flags: did each team play the day before?"""
    df = df.copy()
    last = {}
    hb, ab = [], []
    for r in df.itertuples(index=False):
        hb.append(int(r.home in last and (r.date - last[r.home]).days <= 1))
        ab.append(int(r.away in last and (r.date - last[r.away]).days <= 1))
        last[r.home] = last[r.away] = r.date
    df["home_b2b"], df["away_b2b"] = hb, ab
    return df


class GameModel:
    def __init__(self, half_life_days=60, alpha=1.0, use_rest=True, level_days=35, level_weight=1.0):
        # level_days > 0: nudge both teams' scores so the model matches the league's scoring over the last N days
        self.half_life, self.alpha, self.use_rest, self.level_days, self.level_weight = half_life_days, alpha, use_rest, level_days, level_weight

    def _row(self, off, dfn, home, own_b2b, opp_b2b):
        x = np.zeros(2 * self.n + 3)
        x[self.idx[off]] = 1; x[self.n + self.idx[dfn]] = 1
        x[2 * self.n] = home
        if self.use_rest:
            x[2 * self.n + 1], x[2 * self.n + 2] = own_b2b, opp_b2b
        return x

    def fit(self, games: pd.DataFrame, asof) -> "GameModel":
        asof = pd.Timestamp(asof)
        teams = sorted(set(games.home) | set(games.away))
        self.idx = {t: i for i, t in enumerate(teams)}; self.n = len(teams)
        w = 0.5 ** ((asof - games.date).dt.days.clip(lower=0).to_numpy() / self.half_life)
        X, y, sw = [], [], []
        for r, wi in zip(games.itertuples(index=False), w):
            X.append(self._row(r.home, r.away, 1, r.home_b2b, r.away_b2b)); y.append(r.home_pts); sw.append(wi)
            X.append(self._row(r.away, r.home, 0, r.away_b2b, r.home_b2b)); y.append(r.away_pts); sw.append(wi)
        self.reg = Ridge(alpha=self.alpha).fit(np.array(X), np.array(y), sample_weight=np.array(sw))
        self.level = 0.0
        if self.level_days:
            recent = games[(asof - games.date).dt.days <= self.level_days]
            if len(recent) >= 20:
                pred = sum(sum(self.expected_points(r.home, r.away, r.home_b2b, r.away_b2b)) for r in recent.itertuples(index=False))
                self.level = self.level_weight * float(((recent.home_pts + recent.away_pts).sum() - pred) / len(recent) / 2)   # per team, per game
        return self

    def expected_points(self, home, away, home_b2b=0, away_b2b=0):
        def f(off, dfn, h, ob, pb):
            lv = getattr(self, "level", 0.0)
            if off not in self.idx or dfn not in self.idx:       # a team we know nothing about: league average
                base = np.zeros(2 * self.n + 3); base[2 * self.n] = h
                return float(self.reg.predict(base[None])[0]) + lv
            return float(self.reg.predict(self._row(off, dfn, h, ob, pb)[None])[0]) + lv
        return f(home, away, 1, home_b2b, away_b2b), f(away, home, 0, away_b2b, home_b2b)


# ---- bet probabilities from (mean, sd) of the margin / total. Scores are whole numbers, so use a half-point
# continuity correction. Each returns (win, push). ----
def _cdf(x, mu, sd):
    return stats.norm.cdf((x - mu) / sd)


def p_margin_above(t, mu, sd):
    """P(margin > t) and P(margin == t) for the home margin."""
    if float(t).is_integer():
        return 1 - _cdf(t + .5, mu, sd), _cdf(t + .5, mu, sd) - _cdf(t - .5, mu, sd)
    return 1 - _cdf(t, mu, sd), 0.0


def p_margin_below(t, mu, sd):
    if float(t).is_integer():
        return _cdf(t - .5, mu, sd), _cdf(t + .5, mu, sd) - _cdf(t - .5, mu, sd)
    return _cdf(t, mu, sd), 0.0


def moneyline(mu_margin, sd=SD_MARGIN):
    """Win chances. NBA games cannot end level, so the sliver of 'exactly level' is shared out in proportion."""
    h, a = 1 - _cdf(.5, mu_margin, sd), _cdf(-.5, mu_margin, sd)
    return {"home": float(h / (h + a)), "away": float(a / (h + a))}


def spread(mu_margin, line, side, sd=SD_MARGIN):
    """`line` is the HOME handicap (home -5.5 = home must win by 6+). Away gets the opposite sign."""
    t = -line
    return p_margin_above(t, mu_margin, sd) if side == "home" else p_margin_below(t, mu_margin, sd)


def total(mu_total, line, side, sd=SD_TOTAL):
    return p_margin_above(line, mu_total, sd) if side == "over" else p_margin_below(line, mu_total, sd)
