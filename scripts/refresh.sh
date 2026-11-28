#!/usr/bin/env bash
# One command that brings everything up to date. Run from the repo root.
#   1. restore the saved database   2. download new NBA games + football results
#   3. regenerate predictions       4. safety checks   5. save database
# Each sport is independent: if one fails (e.g. a site blocks us) the other is still refreshed and the failed
# sport keeps its last predictions (the page shows an age warning for it).
# Last line is one of:  REFRESH OK | REFRESH PARTIAL: ... (still safe to publish) | REFRESH FAILED (do not publish)
set -uo pipefail
export PYTHONPATH=src
PY=python3
step() { echo; echo "=== $1"; }
nba_ok=1; soccer_ok=1; us_ok=1

step "Restore saved database";   $PY -m betsuggester.dbtools restore || { echo "REFRESH FAILED: cannot restore database"; exit 1; }
# The two sports are independent, so they run side by side (about half the waiting time).
tmp=$(mktemp -d)
(
  $PY -m betsuggester.ingest 2027 && $PY -m betsuggester.predict
) > $tmp/nba.log 2>&1 && touch $tmp/nba.ok &
(
  $PY -m betsuggester.soccer_ingest 202508 && $PY -m betsuggester.soccer_predict
) > $tmp/soccer.log 2>&1 && touch $tmp/soccer.ok &
(
  $PY -m betsuggester.us_ingest && $PY -m betsuggester.us_predict
) > $tmp/us.log 2>&1 && touch $tmp/us.ok &
wait
step "NBA: new games and predictions";      tail -n 12 $tmp/nba.log;    [ -f $tmp/nba.ok ] && nba_ok=1 || { echo "NBA refresh failed (kept the previous predictions)"; nba_ok=0; }
step "Football: new results and predictions"; tail -n 12 $tmp/soccer.log; [ -f $tmp/soccer.ok ] && soccer_ok=1 || { echo "football refresh failed (kept the previous predictions)"; soccer_ok=0; }
step "NFL + college football: new games and predictions"; tail -n 8 $tmp/us.log; [ -f $tmp/us.ok ] && us_ok=1 || { echo "NFL/college refresh failed (kept the previous predictions)"; us_ok=0; }
step "Recent results (for settling tracked bets)"; $PY -m betsuggester.results || echo "results file failed (tracked bets will wait for the next refresh)"
step "Live scores (a few seconds)"; $PY -m betsuggester.live || echo "live scores failed (harmless)"
step "Club crests (new clubs only)"; $PY -m betsuggester.crests || echo "crest download failed (harmless: the page shows initials badges)"
step "Safety checks";            $PY -m betsuggester.check_outputs; chk=$?
step "Save database";            $PY -m betsuggester.dbtools dump || echo "could not save the database copy (harmless)"

echo
if [ $chk != 0 ]; then echo "REFRESH FAILED: safety checks found invalid data, do not publish"; exit 1; fi
failed=""
[ $nba_ok = 1 ] || failed="$failed NBA"
[ $soccer_ok = 1 ] || failed="$failed football"
[ $us_ok = 1 ] || failed="$failed NFL/college"
if [ -z "$failed" ]; then echo "REFRESH OK"; exit 0; fi
if [ $nba_ok = 1 ] || [ $soccer_ok = 1 ] || [ $us_ok = 1 ]; then echo "REFRESH PARTIAL:$failed failed, the rest refreshed (safe to publish)"; exit 0; fi
echo "REFRESH FAILED: nothing refreshed, do not publish"; exit 1
