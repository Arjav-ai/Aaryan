"""Predict a player's stat (e.g. points) and turn it into P(over a line)."""
import numpy as np
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor

from .features import FEATURES


# How far from a player's recent average we test lines, per stat (bookmaker lines sit near the average).
LINE_OFFSETS = {"pts": (-4, -2, 0, 2, 4), "reb": (-2, -1, 0, 1, 2), "ast": (-2, -1, 0, 1, 2), "fg3": (-1, 0, 1)}
STATS = list(LINE_OFFSETS)


class PropModel:
    def __init__(self, features=None):
        self.features = list(features or FEATURES)
        self.reg = HistGradientBoostingRegressor(loss="poisson", max_iter=250, learning_rate=0.05,
                                                 max_depth=4, min_samples_leaf=40, random_state=0)
        self.alpha = 0.1  # extra spread beyond Poisson (negative-binomial dispersion)

    def fit(self, df, stat="pts"):
        self.reg.fit(df[self.features], df[stat])
        mu = self.reg.predict(df[self.features])
        # Moment estimate: Var(y) = mu + alpha*mu^2
        self.alpha = max(float(np.sum((df[stat] - mu) ** 2 - mu) / np.sum(mu ** 2)), 0.01)
        return self

    def tune_spread(self, df, stat="pts", lines=None):
        """Choose the spread that gives the best-calibrated probabilities on games the regressor did NOT
        train on (stops it being overconfident). `lines`: fixed lines to test (default: NBA-style lines
        around each player's recent average)."""
        mu, y = self.mean(df), df[stat].to_numpy()
        base = df["stat_avg10"].to_numpy()
        tests = [np.full(len(df), c) for c in lines] if lines else [np.floor(base + o) + 0.5 for o in LINE_OFFSETS[stat]]
        best = (np.inf, self.alpha)
        for a in np.linspace(0.02, 0.6, 30):
            self.alpha, ll = a, 0.0
            for line in tests:
                p = np.clip(self.p_over(mu, line), 1e-4, 1 - 1e-4)
                hit = (y > line)
                ll += -np.mean(hit * np.log(p) + (~hit) * np.log(1 - p))
            if ll < best[0]:
                best = (ll, a)
        self.alpha = best[1]
        return self

    def mean(self, df):
        return self.reg.predict(df[self.features])

    def p_over(self, mu, line):
        """P(stat > line) for a half-point line like 24.5."""
        mu = np.asarray(mu, dtype=float)
        n = 1.0 / self.alpha
        p = n / (n + mu)
        return stats.nbinom.sf(np.floor(line), n, p)


def fit_calibrated(train, stat="pts", features=None, lines=None) -> "PropModel":
    """Fit on the older 75% of games, tune the spread on the newest 25% (so probabilities aren't
    overconfident), then refit the regressor on everything."""
    cut = train.date.quantile(0.75)
    m = PropModel(features).fit(train[train.date < cut], stat)
    m.tune_spread(train[train.date >= cut], stat, lines)
    alpha = m.alpha
    m.reg.fit(train[m.features], train[stat])
    m.alpha = alpha
    return m
