"""Football match model: every team gets an attack and a defence strength (plus a home advantage),
estimated from results with recent matches counting more. From the two expected-goals numbers for a
fixture we get the chance of every scoreline, and from that every market: win/draw/loss, handicaps,
total goals, both-teams-to-score.
"""
import numpy as np
import pandas as pd
from scipy import sparse, stats
from sklearn.linear_model import PoissonRegressor

from .db import connect

MAX_GOALS = 10


def load_matches() -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM soccer_matches ORDER BY date", connect())
    df["date"] = pd.to_datetime(df["date"])
    return df


class TeamModel:
    def __init__(self, half_life_days=300, alpha=1e-3, rho=-0.05, disp=0.0, level_days=120):
        # disp > 0 adds spread beyond Poisson (goal counts vary more than Poisson says)
        self.half_life, self.alpha, self.rho, self.disp, self.level_days = half_life_days, alpha, rho, disp, level_days

    def fit(self, matches: pd.DataFrame, asof) -> "TeamModel":
        asof = pd.Timestamp(asof)
        teams = sorted(set(matches.home_id) | set(matches.away_id))
        self.idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        age = (asof - matches.date).dt.days.clip(lower=0).to_numpy()
        w = 0.5 ** (age / self.half_life)
        m = len(matches)
        rows, cols, vals, y = [], [], [], []
        for k, r in enumerate(matches.itertuples(index=False)):
            for side, (att, dfn, goals, home) in enumerate(((r.home_id, r.away_id, r.home_goals, 1),
                                                           (r.away_id, r.home_id, r.away_goals, 0))):
                row = 2 * k + side
                rows += [row, row, row]; cols += [self.idx[att], n + self.idx[dfn], 2 * n]; vals += [1, 1, home]
                y.append(goals)
        X = sparse.csr_matrix((vals, (rows, cols)), shape=(2 * m, 2 * n + 1))
        self.reg = PoissonRegressor(alpha=self.alpha, max_iter=500).fit(X, np.array(y), sample_weight=np.repeat(w, 2))
        c = self.reg.coef_
        self.att, self.dfn, self.home_adv = c[:n], c[n:2 * n], c[2 * n]
        self.n = n
        self.level = 1.0
        if self.level_days:   # re-centre overall goal level on the most recent matches
            recent = matches[(asof - matches.date).dt.days <= self.level_days]
            if len(recent) >= 30:
                pred = sum(sum(self.expected_goals(r.home_id, r.away_id)) for r in recent.itertuples())
                self.level = float((recent.home_goals + recent.away_goals).sum() / pred)
        return self

    def expected_goals(self, home_id, away_id):
        a = lambda t: self.att[self.idx[t]] if t in self.idx else 0.0   # team never seen: average
        d = lambda t: self.dfn[self.idx[t]] if t in self.idx else 0.0
        b = self.reg.intercept_
        lv = getattr(self, 'level', 1.0)
        return float(lv * np.exp(b + a(home_id) + d(away_id) + self.home_adv)), float(lv * np.exp(b + a(away_id) + d(home_id)))

    def score_matrix(self, home_id, away_id) -> np.ndarray:
        lh, la = self.expected_goals(home_id, away_id)
        g = np.arange(MAX_GOALS + 1)
        if self.disp > 0:
            r = 1.0 / self.disp
            pmf = lambda lam: stats.nbinom.pmf(g, r, r / (r + lam))
        else:
            pmf = lambda lam: stats.poisson.pmf(g, lam)
        M = np.outer(pmf(lh), pmf(la))
        # Dixon-Coles correction: low scores are not quite independent
        M[0, 0] *= 1 - lh * la * self.rho; M[0, 1] *= 1 + lh * self.rho
        M[1, 0] *= 1 + la * self.rho; M[1, 1] *= 1 - self.rho
        return M / M.sum()


# ---- markets from a score matrix M[home_goals, away_goals] ----
def outcome_probs(M):
    return {"home": float(np.tril(M, -1).sum()), "draw": float(np.trace(M)), "away": float(np.triu(M, 1).sum())}


def handicap_prob(M, line):
    """Home team's chance of covering handicap `line` (e.g. -1.5 = must win by 2+). Returns (win, push)."""
    i, j = np.indices(M.shape)
    diff = i - j + line
    return float(M[diff > 0].sum()), float(M[diff == 0].sum())


def total_prob(M, line):
    """Chance of MORE than `line` total goals. Returns (over, push)."""
    i, j = np.indices(M.shape)
    tot = i + j
    return float(M[tot > line].sum()), float(M[tot == line].sum())


def btts_prob(M):
    return float(M[1:, 1:].sum())
