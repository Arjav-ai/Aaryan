# Bet Suggester

Personal tool that estimates the probability of NBA player props hitting (points, rebounds, assists,
threes), then lets you type in a bookmaker's line and odds to see if a bet is worth taking.

Two sections planned:
1. **Best bets** – props where the model's probability beats the odds you enter.
2. **Most probable bets** – props most likely to hit, filtered to odds above a minimum you set.

## Status
- [x] NBA data downloader (Basketball-Reference, cached, rate-limited)
- [x] Points, rebounds, assists, threes models + back-test (src/betsuggester/backtest.py)
- [x] Web page for iPhone (Best bets + Most probable, your own line and odds)
- [x] Football: 6 competitions - match model (1X2, handicap, goals, both-teams-score), player props (shots, shots on target, goals, assists), league outrights
- [ ] American football (NFL + college), tennis

## Run the data download
```
pip install -r requirements.txt
PYTHONPATH=src python -m betsuggester.ingest 2027   # 2027 = 2026-27 season
PYTHONPATH=src python -m pytest -q tests
```
Safe to re-run daily: only new games are fetched. Data lands in `data/` (not committed).

This tool only suggests; it doesn't place bets. Probabilities are model estimates, not guarantees.

## The iPhone page
`site/index.html` is a single page that loads `predictions.json` and does the odds maths in the browser.
Refresh routine (ask Claude to "refresh", or run it yourself):
```
PYTHONPATH=src python -m betsuggester.ingest 2027     # new games only
PYTHONPATH=src python -m betsuggester.predict         # writes data/predictions.json
# then republish site/index.html together with data/predictions.json
```

## Testing the page
`tests/e2e/site.test.js` drives the page in a real browser (47 checks: filters, minimum odds, typing line/odds,
saved settings, bad input, failed load, stale warning, dark mode, phone widths). To run it:
```
cd site && cp ../data/predictions.json . && python -m http.server 8765 &
node tests/e2e/site.test.js <output-folder>     # needs: npm i playwright
```


## Football (soccer)
```
PYTHONPATH=src python -m betsuggester.soccer_ingest 202508     # matches + player stats from ESPN (fast, parallel)
PYTHONPATH=src python -m betsuggester.soccer_predict           # writes data/predictions_soccer.json
PYTHONPATH=src python -m betsuggester.soccer_backtest          # match model on unseen matches
PYTHONPATH=src python -m betsuggester.soccer_props 2026-02-01  # player props on unseen matches
PYTHONPATH=src python -m betsuggester.soccer_retro 2025-11-24  # league simulation vs how last season ended
```
Browser tests: `tests/e2e/nba.test.js` (47 checks) and `tests/e2e/football.test.js` (63 checks).

### Champions League outrights
League phase only (top 8 / playoff 9-24 / out 25-36). Trophy chances are deliberately NOT shown until the knockout
draw has been made: `soccer_predict.knockout_draw_done()` checks ESPN for knockout fixtures between named teams, and
the page says so until then. Retro test: `python -m betsuggester.soccer_retro cl 2025-11-26`.

## Automatic refresh
`scripts/refresh.sh` does everything in one go (restore saved database -> download new NBA games and football
results -> regenerate predictions -> safety checks -> save database). It works from an empty copy of the repo in
about 4 minutes. A scheduled Claude task runs it twice a day (5 pm and 12 am India time, started ~18 minutes early)
and republishes the page only if the checks pass. The database is kept as text in `data/db_dump.sql` so git history stays small.

### Refresh now button
The page has a "Refresh now" button that starts the same scheduled refresh through the Claude Code Remote connector
(`fire_trigger`). The schedule's id is hard-coded in `site/index.html` (`RF.trigger`): if the schedule is ever deleted
and recreated, update that id and republish with `capabilities: {mcp: {servers: [{server: "Claude Code Remote", tools: ["fire_trigger"]}]}}`.
Browser test with a stand-in connector: `tests/e2e/refresh.test.js` (30 checks).

### Football screens and crests
Football > Matches is a list of upcoming matches (grouped by day, filter by league or team). Tapping a match opens its page:
**Player props** (both teams, filter by team or stat) and **Match bets** (result, handicap, goals, both teams to score).
Club crests are 96px PNGs from ESPN in `site/crests/<ESPN team id>.png`, downloaded by `python -m betsuggester.crests`
and published with the page. A club with no crest shows an initials badge. The scheduled refresh republishes only the page
and the two data files, so a brand-new club shows initials until the crests are published again by hand.
Phone layout: the page leaves 44px under the status bar for the Claude app's floating buttons (`--chrome`), keeps its 16px
side gutters on `.wrap`, and keeps the sticky header compact. Test: `tests/e2e/phone-layout.test.js`.
Browser tests: `nba.test.js` (47), `football.test.js` (89), `refresh.test.js` (30), `started.test.js`.

### NBA games
NBA > Games works like Football > Matches: a list of upcoming games with team logos (away team first), tap one for its
page with every player's props for both teams, a "ruled out" notice per team, and team / stat filters. NBA has no game-level
model, so the list shows no win percentages. Logos are `site/crests/nba/<code>.png` (30 teams, `python -m betsuggester.crests`).
Browser tests: `tests/e2e/nba-games.test.js` (38 checks).
