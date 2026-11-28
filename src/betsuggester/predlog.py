"""Keep a frozen copy of what the models predicted BEFORE each game, so they can be marked against real results later
(a forward test: nothing here can be tuned after the fact).

Usage: python -m betsuggester.predlog
Each refresh overwrites the entry of a game that has not started yet; once it has started the entry is frozen.
Entries older than 150 days are dropped. File: data/prediction_log.json
"""
import datetime as dt
import json
import math
from pathlib import Path

LOG = Path("data/prediction_log.json")
FILES = {"nba": "data/predictions.json", "nfl": "data/predictions_nfl.json", "cfb": "data/predictions_cfb.json",
         "tennis": "data/predictions_tennis.json", "football": "data/predictions_soccer.json"}
KEEP_DAYS = 150


def _ndtr(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def _ml(mu, sd):                       # the page's moneyline formula
    h = 1 - _ndtr((0.5 - mu) / sd); a = _ndtr((-0.5 - mu) / sd)
    return h / (h + a)


def game_entry(sport, g):
    e = {"sport": sport, "id": str(g["id"]), "start": g["start"], "date": g.get("date"), "home": g.get("home"), "away": g.get("away")}
    if g.get("grid"):                                  # football: scoreline grid
        grid = g["grid"]; n = len(grid)
        e["p_home"] = round(sum(grid[i][j] for i in range(n) for j in range(n) if i > j), 4)
        e["p_draw"] = round(sum(grid[i][i] for i in range(n)), 4)
        e["mu_total"] = round(sum(grid[i][j] * (i + j) for i in range(n) for j in range(n)), 3)
        e["p_over25"] = round(sum(grid[i][j] for i in range(n) for j in range(n) if i + j > 2.5), 4)
    elif g.get("nba"):
        nb = g["nba"]
        e["p_home"] = round(g["p_home"] if sport == "tennis" else _ml(nb["mu_margin"], nb["sd_margin"]), 4)
        e["mu_total"], e["sd_total"] = nb["mu_total"], nb["sd_total"]
    else:
        return None
    return e


def main():
    log = json.loads(LOG.read_text()) if LOG.exists() else {"games": {}, "props": {}}
    now = dt.datetime.now(dt.timezone.utc)
    added = 0
    for sport, path in FILES.items():
        f = Path(path)
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        upcoming = {}
        for g in d["games"]:
            start = dt.datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
            if start <= now:
                continue                                # already started: keep what was logged before
            e = game_entry(sport, g)
            if e:
                key = f"{sport}:{g['id']}"; log["games"][key] = e; upcoming[str(g["id"])] = key; added += 1
        for key in {k for k in upcoming.values()}:
            log["props"][key] = []                      # rebuilt below from the current file
        for p in d.get("players", []):
            key = upcoming.get(str(p["game"]))
            if key is None:
                continue
            for stat, v in p["stats"].items():
                log["props"][key].append([p["name"], stat, v["mu"], v["alpha"]])
    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for k in [k for k, e in log["games"].items() if e["start"] < cutoff[:16]]:
        log["games"].pop(k, None); log["props"].pop(k, None)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log, separators=(",", ":")))
    print(f"prediction log: {len(log['games'])} games ({added} refreshed now), {sum(len(v) for v in log['props'].values())} prop predictions, {LOG.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
