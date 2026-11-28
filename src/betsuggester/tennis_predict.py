"""Predictions for upcoming ATP and WTA singles matches -> data/predictions_tennis.json (same shape the NBA page reads).

Usage: python -m betsuggester.tennis_predict
Match winner from Elo ratings; handicap and total-games centre/spread from the game-by-game simulation, with the
corrections measured in tennis_backtest.py.
"""
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from . import tennis_model as T

OUT = Path("data/predictions_tennis.json")
MIN_MATCHES = 4          # both players need this many matches in the data, otherwise the rating is a guess


def main():
    games, through = [], None
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    for tour in ("atp", "wta"):
        df = T.load(tour)
        wf, elo = T.walk_forward(df, tour)
        through = max(through or df[df.state == "post"].date.max(), df[df.state == "post"].date.max())
        up = df[(df.state == "pre") & (df.date >= now - pd.Timedelta(hours=1)) & (df.date <= now + pd.Timedelta(days=4))]
        for r in up.itertuples(index=False):
            if elo.n.get(r.p1_id, 0) < MIN_MATCHES or elo.n.get(r.p2_id, 0) < MIN_MATCHES:
                continue
            p = elo.predict(r.p1_id, r.p2_id)
            bo = int(r.best_of)
            mk = T.match_markets(p, tour, bo)
            games.append({"id": r.match_id, "start": r.date.strftime("%Y-%m-%dT%H:%MZ"), "date": r.date.strftime("%Y-%m-%d"),
                          "home": r.p1, "away": r.p2, "home_name": r.p1, "away_name": r.p2, "home_id": r.p1_id, "away_id": r.p2_id,
                          "league": tour, "league_name": f"{tour.upper()} · {r.tournament}", "best_of": bo,
                          "p_home": round(p, 4), "elo_home": round(elo.rating(r.p1_id)), "elo_away": round(elo.rating(r.p2_id)),
                          "nba": {**mk, "mu_home": 0, "mu_away": 0, "home_b2b": 0, "away_b2b": 0, "adj_margin": 0, "adj_notes": []}})
    games.sort(key=lambda g: g["start"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                               "data_through": str(pd.Timestamp(through).date()), "labels": {}, "stats": [], "games": games, "players": []}, separators=(",", ":")))
    print(f"wrote {OUT}: {len(games)} upcoming matches")


if __name__ == "__main__":
    main()
