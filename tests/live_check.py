"""Checks for live.py (needs internet). Run: PYTHONPATH=src python3 tests/live_check.py
Box-score extraction is checked against final scores of finished games; the clock maths against hand-worked cases;
and the whole script is run once so a crash on import or on live data cannot go unnoticed."""
import subprocess, sys
from betsuggester import espn, live

bad = 0
def check(name, ok, detail=""):
    global bad
    bad += not ok
    print("PASS" if ok else "FAIL", name, detail)

sb = espn.get("basketball/nba/scoreboard", ttl=0, dates="20261127")
done = [e for e in sb["events"] if e["status"]["type"]["completed"]][:3]
for ev in done:
    got = live.box_stats("nba", espn.get("basketball/nba/summary", ttl=0, event=ev["id"]), {"id": ev["id"]})
    total = sum(int(c["score"]) for c in ev["competitions"][0]["competitors"])
    check(f"NBA points of all players add up to the final score ({ev['name']})", sum(v["pts"] for v in got.values()) == total, f"{sum(v['pts'] for v in got.values())} vs {total}")
sb = espn.get("soccer/eng.1/scoreboard", ttl=0, dates="20261127")
for ev in [e for e in sb["events"] if e["status"]["type"]["completed"]][:1]:
    c = {x["homeAway"]: x for x in ev["competitions"][0]["competitors"]}
    got = live.box_stats("football", espn.get("soccer/eng.1/summary", ttl=0, event=ev["id"]), {"id": ev["id"], "home_id": c["home"]["team"]["id"], "away_id": c["away"]["team"]["id"], "home": "", "away": ""})
    check("soccer goals of all players add up to the final score", sum(v["goals"] for v in got.values()) == sum(int(x["score"]) for x in c.values()))
for args, want in [(("nba", 1, "12:00"), 0.0), (("nba", 2, "6:00"), 0.375), (("nba", 4, "0:00"), 0.995), (("nfl", 3, "7:30"), 0.625), (("cfb", 1, "15:00"), 0.0), (("football", 2, "", "67'"), 67 / 90)]:
    check(f"elapsed fraction {args}", abs(live.elapsed_fraction(*args) - want) < 0.011, f"{live.elapsed_fraction(*args):.3f} vs {want:.3f}")
check("names match across accents and suffixes", live.norm("Nikola Jokić Jr.") == "nikola jokic" and live.norm("D'Angelo Russell") == "dangelo russell")
r = subprocess.run([sys.executable, "-m", "betsuggester.live"], capture_output=True, text=True)
check("the script runs end to end", r.returncode == 0 and "ACTIVE=" in r.stdout, (r.stderr or r.stdout)[-160:])
print(f"{bad} failed" if bad else "all passed")
raise SystemExit(1 if bad else 0)
