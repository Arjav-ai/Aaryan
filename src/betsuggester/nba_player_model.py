"""NBA game model built from PLAYER ratings, so a star being out changes the prediction.

Each player gets an offence and a defence rating (points per game he adds / removes for his team when he plays
the whole game). A team's expected score = baseline + sum over its players of (offence rating x share of the
team's minutes) + sum over the opponent's players of (defence rating x share of THEIR minutes).
Minutes shares come from each player's recent average, so tonight's lineup (who is in, who is out) is the input.
"""
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge

from .db import connect
from .nba_game_model import add_rest, load_games

DEFAULT_MIN = 10.0     # a player with no history is treated like a bench player


def load_lineups() -> pd.DataFrame:
    """One row per player-game with the player's AVERAGE minutes over his previous 10 games (what a coach/oddsmaker
    would expect before tip-off), never the minutes he actually played in that game."""
    pg = pd.read_sql_query("""SELECT p.game_id, p.team, p.is_home, p.player, p.minutes, g.date FROM player_games p JOIN games g USING (game_id)
                              ORDER BY g.date, p.game_id""", connect())
    pg["date"] = pd.to_datetime(pg["date"])
    pg["pre_min"] = pg.groupby("player")["minutes"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).mean()).fillna(DEFAULT_MIN)
    return pg[pg.minutes > 0]


class PlayerGameModel:
    def __init__(self, half_life_days=90, alpha=60.0, level_days=35):
        self.half_life, self.alpha, self.level_days = half_life_days, alpha, level_days

    def _design(self, rows):
        """rows: list of (own_lineup, opp_lineup, home, own_b2b, opp_b2b); lineup = [(player, minutes), ...]."""
        data, ri, ci = [], [], []
        P = self.np
        for r, (own, opp, home, ob, pb) in enumerate(rows):
            for lineup, off in ((own, True), (opp, False)):
                tot = sum(m for _, m in lineup) or 1.0
                for pl, m in lineup:
                    j = self.pidx.get(pl)
                    if j is None:
                        continue
                    data.append(m / tot); ri.append(r); ci.append(j if off else P + j)
            data += [home, ob, pb]; ri += [r, r, r]; ci += [2 * P, 2 * P + 1, 2 * P + 2]
        return sparse.csr_matrix((data, (ri, ci)), shape=(len(rows), 2 * P + 3))

    def fit(self, games: pd.DataFrame, lineups: pd.DataFrame, asof):
        asof = pd.Timestamp(asof)
        games = games[games.date < asof]
        lu = {k: list(zip(g.player, g.pre_min)) for k, g in lineups[lineups.game_id.isin(games.game_id)].groupby(["game_id", "team"])}
        players = sorted(lineups[lineups.game_id.isin(games.game_id)].player.unique())
        self.pidx = {p: i for i, p in enumerate(players)}; self.np = len(players)
        rows, y, w = [], [], []
        for r in games.itertuples(index=False):
            h, a = lu.get((r.game_id, r.home), []), lu.get((r.game_id, r.away), [])
            wt = 0.5 ** (max((asof - r.date).days, 0) / self.half_life)
            rows.append((h, a, 1, r.home_b2b, r.away_b2b)); y.append(r.home_pts); w.append(wt)
            rows.append((a, h, 0, r.away_b2b, r.home_b2b)); y.append(r.away_pts); w.append(wt)
        self.reg = Ridge(alpha=self.alpha).fit(self._design(rows), np.array(y), sample_weight=np.array(w))
        self.level = 0.0
        if self.level_days:
            rec = games[(asof - games.date).dt.days <= self.level_days]
            if len(rec) >= 20:
                pred = 0.0
                for r in rec.itertuples(index=False):
                    h, a = lu.get((r.game_id, r.home), []), lu.get((r.game_id, r.away), [])
                    pred += sum(self.expected_points(h, a, r.home_b2b, r.away_b2b))
                self.level = float(((rec.home_pts + rec.away_pts).sum() - pred) / len(rec) / 2)
        return self

    def team_points(self, own, opp, home, ob=0, pb=0):
        return float(self.reg.predict(self._design([(own, opp, home, ob, pb)]))[0]) + getattr(self, "level", 0.0)

    def expected_points(self, home_lineup, away_lineup, home_b2b=0, away_b2b=0):
        return self.team_points(home_lineup, away_lineup, 1, home_b2b, away_b2b), self.team_points(away_lineup, home_lineup, 0, away_b2b, home_b2b)
