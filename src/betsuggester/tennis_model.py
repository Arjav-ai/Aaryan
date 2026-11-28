"""Tennis model: Elo ratings for who wins, and a game-by-game simulation for how many games it takes.

1. Elo (separate for each tour), updated match by match; every match is predicted only from earlier matches.
2. For a predicted win chance p, the simulation finds how much better player A holds serve than player B
   (around the tour's average hold rate) so that A wins the match with probability p. That gives a consistent
   expected total games, spread of total games and spread of the games margin, which the page turns into
   match-winner, games-handicap and total-games chances.
"""
import math
from functools import lru_cache

import numpy as np
import pandas as pd

from .db import connect

K0, KN, KEXP = 250.0, 5.0, 0.4          # Elo update size: K = K0 / (matches + KN) ** KEXP
HOLD = {"atp": 0.80, "wta": 0.64}       # average hold of serve; refined in tennis_backtest.py
SCALE = {"atp": 0.0030, "wta": 0.0045}  # logistic slope on Elo difference (about ln(10)/400 = 0.00576 is the classic value)


def load(tour: str) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM tennis_matches WHERE tour=? ORDER BY date, match_id", connect(), params=(tour,))
    df["date"] = pd.to_datetime(df["date"])
    return df


def win_prob(d, scale):
    return 1.0 / (1.0 + math.exp(-scale * d))


class Elo:
    def __init__(self, tour):
        self.r, self.n, self.scale = {}, {}, SCALE[tour]

    def rating(self, pid):
        return self.r.get(pid, 1500.0)

    def predict(self, a, b):
        return win_prob(self.rating(a) - self.rating(b), self.scale)

    def update(self, a, b, a_won: bool):
        p = self.predict(a, b)
        for pid, won in ((a, a_won), (b, not a_won)):
            k = K0 / (self.n.get(pid, 0) + KN) ** KEXP
            sign = 1.0 if pid == a else -1.0
            self.r[pid] = self.rating(pid) + k * ((1.0 if won else 0.0) - (p if pid == a else 1 - p))
            self.n[pid] = self.n.get(pid, 0) + 1


def walk_forward(df: pd.DataFrame, tour: str):
    """Predict every finished match from earlier ones only. -> DataFrame with p (chance player 1 wins)."""
    elo = Elo(tour); rows = []
    for r in df.itertuples(index=False):
        if r.state != "post" or r.winner == 0 or r.status in ("Walkover", "Canceled"):
            continue
        p = elo.predict(r.p1_id, r.p2_id)
        rows.append((r.match_id, r.date, p, int(r.winner == 1), min(elo.n.get(r.p1_id, 0), elo.n.get(r.p2_id, 0))))
        elo.update(r.p1_id, r.p2_id, r.winner == 1)
    return pd.DataFrame(rows, columns=["match_id", "date", "p", "y", "min_n"]), elo


# ---------- games model ----------
def _set_dist(hA, hB, first, ptb):
    """Distribution of one set: {(gamesA, gamesB): prob}. first = who serves game 1 (0 = A). Tiebreak at 6-6 (A wins it with ptb)."""
    out = {}
    state = {(0, 0): 1.0}
    for _ in range(14):
        nxt = {}
        for (a, b), pr in state.items():
            if (a >= 6 or b >= 6) and abs(a - b) >= 2 or (a == 7 or b == 7):
                out[(a, b)] = out.get((a, b), 0.0) + pr; continue
            if a == 6 and b == 6:
                nxt[(7, 6)] = nxt.get((7, 6), 0.0) + pr * ptb
                nxt[(6, 7)] = nxt.get((6, 7), 0.0) + pr * (1 - ptb)
                continue
            server = (first + a + b) % 2
            pa = hA if server == 0 else 1 - hB          # chance A wins this game
            nxt[(a + 1, b)] = nxt.get((a + 1, b), 0.0) + pr * pa
            nxt[(a, b + 1)] = nxt.get((a, b + 1), 0.0) + pr * (1 - pa)
        state = nxt
        if not state:
            break
    for k, v in state.items():
        out[k] = out.get(k, 0.0) + v
    return out


@lru_cache(maxsize=20000)
def match_stats(hA, hB, best_of):
    """-> (P(A wins), mean total games, sd total games, mean games margin A-B, sd games margin)."""
    ptb = 0.5 + 0.5 * ((hA - (1 - hB)) / 2.0)           # a slightly better server/returner mix wins the tiebreak a bit more often
    need = best_of // 2 + 1
    state = {(0, 0, 0, 0, 0): 1.0}                       # (setsA, setsB, who serves next set's first game, gamesA, gamesB)
    pw = tg = tg2 = mg = mg2 = 0.0
    for _ in range(best_of):
        nxt = {}
        for (sa, sb, first, ga, gb), pr in state.items():
            if sa == need or sb == need:
                nxt[(sa, sb, first, ga, gb)] = nxt.get((sa, sb, first, ga, gb), 0.0) + pr; continue
            for (a, b), q in _set_dist(hA, hB, first, ptb).items():
                f2 = (first + a + b) % 2
                key = (sa + (a > b), sb + (b > a), f2, ga + a, gb + b)
                nxt[key] = nxt.get(key, 0.0) + pr * q
        state = nxt
    for (sa, sb, first, ga, gb), pr in state.items():
        pw += pr * (sa > sb); t = ga + gb; m = ga - gb
        tg += pr * t; tg2 += pr * t * t; mg += pr * m; mg2 += pr * m * m
    return pw, tg, math.sqrt(max(tg2 - tg * tg, 1e-9)), mg, math.sqrt(max(mg2 - mg * mg, 1e-9))


def for_win_prob(p, h0, best_of):
    """Find hold rates (h0 + d, h0 - d) so player A wins with chance p. -> match_stats at that point."""
    lo, hi = -0.3, 0.3
    p = min(max(p, 0.01), 0.99)
    for _ in range(22):
        mid = (lo + hi) / 2
        pw = match_stats(round(min(max(h0 + mid, 0.3), 0.97), 5), round(min(max(h0 - mid, 0.3), 0.97), 5), best_of)[0]
        lo, hi = (mid, hi) if pw < p else (lo, mid)
    d = (lo + hi) / 2
    return match_stats(round(min(max(h0 + d, 0.3), 0.97), 5), round(min(max(h0 - d, 0.3), 0.97), 5), best_of)


# Corrections found in tennis_backtest.py (fitted on 2025 matches, checked on 2026): the simulation runs high on total games and the
# real distribution leans to the right (some matches go long), so the centre of the page's bell curve is moved to the median.
# (tour, best_of) -> (shift in games, spread in games)
TOTAL_FIX = {("atp", 3): (-3.29, 6.52), ("atp", 5): (-6.12, 10.37), ("wta", 3): (-3.37, 6.26)}
MARGIN_SD_SCALE = {("atp", 3): 1.16, ("atp", 5): 1.24, ("wta", 3): 1.22}


def _ndtr(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def _ml_from_margin(mu, sd):
    """The page's moneyline formula (it counts whole-game margins): chance player 1 wins given margin ~ Normal(mu, sd)."""
    h = 1 - _ndtr((0.5 - mu) / sd)
    a = _ndtr((-0.5 - mu) / sd)
    return h / (h + a)


def match_markets(p, tour, best_of):
    """Everything the page needs for a match from player 1's win chance p -> dict of centre/spread for margin and total games."""
    key = (tour, best_of if (tour, best_of) in TOTAL_FIX else 3)
    pw, mt, st, mm, sm = for_win_prob(round(float(p) * 100) / 100, HOLD[tour], key[1])
    shift, sd_t = TOTAL_FIX[key]
    sd_m = sm * MARGIN_SD_SCALE[key]
    lo, hi = -30.0, 30.0
    for _ in range(50):                      # centre the margin so the page's moneyline equals the Elo chance exactly
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _ml_from_margin(mid, sd_m) < p else (lo, mid)
    return {"mu_total": round(mt + shift, 2), "sd_total": round(sd_t, 2), "mu_margin": round((lo + hi) / 2, 2), "sd_margin": round(sd_m, 2)}
