#!/usr/bin/env bash
# One command that brings everything up to date. Run from the repo root.
#   1. restore the saved database   2. download new NBA games + football results
#   3. regenerate predictions       4. safety checks   5. save the database
# Exits non-zero if anything looks wrong, so nothing bad gets published.
set -uo pipefail
export PYTHONPATH=src
step() { echo; echo "=== $1"; }
fail=0

step "Restore saved database";            python3 -m betsuggester.dbtools restore || exit 1
step "NBA: new games";                    python3 -m betsuggester.ingest 2027 || { echo "NBA download failed"; fail=1; }
step "Football: new results";             python3 -m betsuggester.soccer_ingest 202508 || { echo "football download failed"; fail=1; }
step "NBA predictions";                   python3 -m betsuggester.predict || { echo "NBA predictions failed (kept the previous ones)"; fail=1; }
step "Football predictions";              python3 -m betsuggester.soccer_predict || { echo "football predictions failed (kept the previous ones)"; fail=1; }
step "Safety checks";                     python3 -m betsuggester.check_outputs || fail=1
step "Save database";                     python3 -m betsuggester.dbtools dump || fail=1
echo; [ $fail = 0 ] && echo "REFRESH OK" || echo "REFRESH HAD PROBLEMS: do not publish"
exit $fail
