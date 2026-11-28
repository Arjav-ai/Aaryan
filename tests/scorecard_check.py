"""Independent check of scorecard.py: build a fake prediction log from real finished games, compute the expected numbers
by hand (numpy only, different code path), and compare. Run: PYTHONPATH=src python3 tests/scorecard_check.py"""
import json, math, sqlite3, tempfile
from pathlib import Path
import numpy as np
from betsuggester import scorecard as S

c = sqlite3.connect("data/nba.sqlite")
games = c.execute("SELECT game_id, home_pts, away_pts, date, home_abbr FROM us_games WHERE league='nfl' AND season=2026 ORDER BY date LIMIT 12").fetchall()
log = {"games": {}, "props": {}}
rng = np.random.default_rng(3)
exp_p, exp_y, exp_over_p, exp_over_y, prop_p, prop_y = [], [], [], [], [], []
for gid, hp, ap, date, habb in games:
    p = float(np.round(rng.uniform(0.2, 0.9), 3)); mu_total = 44.0; sd = 13.8
    log["games"][f"nfl:{gid}"] = {"sport": "nfl", "id": gid, "start": date + "T18:00Z", "date": date, "home": habb, "away": "X", "p_home": p, "mu_total": mu_total, "sd_total": sd}
    exp_p.append(p); exp_y.append(1.0 if hp > ap else 0.0)
    line = 44.5; z = (line - mu_total) / sd
    exp_over_p.append(1 - 0.5 * math.erfc(-z / math.sqrt(2))); exp_over_y.append(1.0 if hp + ap > line else 0.0)
    # props: every receiver in this game with rec_yds > 0 gets mu 40, alpha .5, line floor(40)+.5 = 40.5
    rows = c.execute("SELECT player, rec_yds FROM us_player_games WHERE game_id=? AND league='nfl' AND rec_yds>0", (gid,)).fetchall()
    log["props"][f"nfl:{gid}"] = [[n, "rec_yds", 40.0, 0.5] for n, y in rows]
    r = 1 / 0.5; pr = r / (r + 40.0)
    pmf = [math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1) + r * math.log(pr) + k * math.log(1 - pr)) for k in range(41)]
    p_over = 1 - sum(pmf)
    for n, y in rows:
        prop_p.append(p_over); prop_y.append(1.0 if y > 40.5 else 0.0)
tmp = Path(tempfile.mkdtemp())
S.LOG = tmp / "log.json"; S.OUT = tmp / "out.json"; S.LOG.write_text(json.dumps(log))
S.main()
out = json.loads(S.OUT.read_text())["sports"]["nfl"]
p, y = np.array(exp_p), np.array(exp_y)
checks = [
    ("settled games", out["settled"], len(games)),
    ("brier", out["games"]["brier"], round(float(((p - y) ** 2).mean()), 4)),
    ("logloss", out["games"]["logloss"], round(float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()), 4)),
    ("winner right", out["games"]["winner_right"], round(float(((p > .5) == (y == 1)).mean()), 3)),
    ("totals said over", out["totals"]["said_over"], round(float(np.mean(exp_over_p)), 3)),
    ("totals happened over", out["totals"]["happened_over"], round(float(np.mean(exp_over_y)), 3)),
    ("props n", out["props"]["n"], len(prop_p)),
    ("props said over", out["props"]["said_over"], round(float(np.mean(prop_p)), 3)),
    ("props happened over", out["props"]["happened_over"], round(float(np.mean(prop_y)), 3)),
]
bad = 0
for name, got, want in checks:
    ok = got == want; bad += not ok
    print("PASS" if ok else "FAIL", name, got, want)
print("bins sum to games:", sum(b["n"] for b in out["games"]["bins"]) == len(games))
print(f"{len(checks) - bad} passed, {bad} failed")
raise SystemExit(1 if bad else 0)
