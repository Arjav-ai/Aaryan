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
nba_ok=1; soccer_ok=1

step "Restore saved database";   $PY -m betsuggester.dbtools restore || { echo "REFRESH FAILED: cannot restore database"; exit 1; }
step "NBA: new games";           $PY -m betsuggester.ingest 2027 || { echo "NBA download failed"; nba_ok=0; }
step "Football: new results";    $PY -m betsuggester.soccer_ingest 202508 || { echo "football download failed"; soccer_ok=0; }
if [ $nba_ok = 1 ]; then step "NBA predictions";      $PY -m betsuggester.predict || { echo "NBA predictions failed (kept the previous ones)"; nba_ok=0; }; fi
if [ $soccer_ok = 1 ]; then step "Football predictions"; $PY -m betsuggester.soccer_predict || { echo "football predictions failed (kept the previous ones)"; soccer_ok=0; }; fi
step "Safety checks";            $PY -m betsuggester.check_outputs; chk=$?
step "Save database";            $PY -m betsuggester.dbtools dump || echo "could not save the database copy (harmless)"

echo
if [ $chk != 0 ]; then echo "REFRESH FAILED: safety checks found invalid data, do not publish"; exit 1; fi
if [ $nba_ok = 1 ] && [ $soccer_ok = 1 ]; then echo "REFRESH OK"; exit 0; fi
if [ $nba_ok = 1 ]; then echo "REFRESH PARTIAL: football failed, NBA refreshed (safe to publish)"; exit 0; fi
if [ $soccer_ok = 1 ]; then echo "REFRESH PARTIAL: NBA failed, football refreshed (safe to publish)"; exit 0; fi
echo "REFRESH FAILED: neither sport refreshed, do not publish"; exit 1
