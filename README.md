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
model, so the list shows no win percentages. (Superseded: see NBA game model below.) Logos are `site/crests/nba/<code>.png` (30 teams, `python -m betsuggester.crests`).
Browser tests: `tests/e2e/nba-games.test.js` (38 checks).

### NBA game model (moneyline / spread / total points)
`src/betsuggester/nba_game_model.py` predicts each team's score from attack/defence ratings (ridge regression, 60-day memory),
home court and back-to-backs, with a level adjustment from the last 35 days. Margin and total are treated as normal with a
spread of 15 / 19 points (measured out of sample). Playoff games are excluded (they score ~15 points fewer).
`python -m betsuggester.nba_game_backtest 2026-01-01` re-runs the walk-forward test (991 unseen regular-season games):
picks the winner 68.8%, moneyline log-loss 0.592 vs 0.689 for a flat guess, spread 0.636 vs 0.711, total 0.639 vs 0.676;
calibration tables printed alongside. The typical miss (15 points on the margin) is much larger than a bookmaker's because the model
knows nothing about injuries or lineups. `tests/e2e/nba_game_check.py` checks the page's numbers against this Python model.

### How precise is the NBA game model? (measured against the bookmaker)
`python -m betsuggester.nba_lines` downloads DraftKings' pre-game spread / total / moneyline from ESPN for past games (1,281 of 1,580);
`python -m betsuggester.nba_market_benchmark` compares our walk-forward predictions with them on the same unseen games
(959 regular-season games since 2026-01-01). Result: typical margin miss 11.65 pts (bookmaker 10.93, flat guess 13.50); std of the
miss 14.9 vs 14.0; winner picked 69.2% vs 71.5%; moneyline log-loss 0.592 vs 0.552. Regression of the outcome on line and model:
model weight -0.14 +/- 0.22, i.e. nothing beyond the line. Pretend flat bets on every disagreement with the spread: -1.9% per bet
(-0.6% at edge >= 10%); with ~1,000 bets the error bar is about +/-3%, so this cannot prove "no edge" but shows no sign of one.
An earlier version of the page said the model was "well above what betting markets achieve" (~15 vs ~11-12): wrong, the bookmaker's own
std of miss is ~14.0 on these games. Fixed.

### Record (scoreboard) and injuries in the NBA game model
**Record**: type odds on a prop / game bet / outright, tap "Track bet", and the Record page settles it from `results.json`
(final scores + player stats for the last 21 days, written by `python -m betsuggester.results` on every refresh) at 1 unit per bet.
It shows profit, return per bet with an honest error bar, what the model *expected* from those same bets (so you can see whether
the gap is luck), and a calibration table (model chance vs how often it won). The ledger is one private document per viewer
(`data/users/<id>/ledger`, `db` + `user` capabilities), with a localStorage fallback. Void: player did not play. Push: line hit exactly.
Browser test with a stand-in database and crafted scores: `tests/e2e/record.test.js` (38 checks).

**Injuries**: `nba_injury_adjust.py` lowers a team's expected margin by 0.046 points per unit of "talent" ruled out (talent = points +
1.2 rebounds + 1.5 assists per game, last 10 games) x how often he normally plays x the chance he sits (Out 100%, Doubtful 85%,
Questionable 50%, Day-to-Day 40%; the last three are untested judgement calls). Measured on 959 unseen games with lineups known:
typical margin miss 11.65 -> 11.54 points (bookmaker 10.93). Player-by-player ratings were tried first and were worse (13.4)
because there is too little data per player. `python -m betsuggester.nba_injury_backtest` reproduces the numbers.

### Europa League and Conference League; last 5 games on every prop
Football now covers the Europa League (`uefa.europa`) and Conference League (`uefa.europa.conf`) besides the Champions League:
matches, player props and league-phase outrights (top 8 / playoff 9-24 / out 25-36; trophy chances still held until the knockout draw).
`soccer_outrights.CUPS` holds each cup's name and last league-phase day. Retro test on last season at the same stage
(`python -m betsuggester.soccer_retro cup uefa.europa 2025-11-27 2026-01-29`): Europa beat a flat guess on all three bands,
Conference on top 8 and out only (its middle band is no better than flat). Clubs from outside the big five leagues have only their
European matches in the data, so their numbers are less reliable.
Every prop row (inside a match / game page, Best bets and Most probable) shows its last 5 games coloured against the line,
with "N of 5 over/under L" updating as the line changes.

## Offered line and verdict

Every prop row has three boxes: Line offered, Over odds, Under odds. Type what the bookmaker shows and the page says in plain words how good the bet is (edge = model chance minus the chance the price needs). The line is shared by both sides. Verdict thresholds are judgement, not tested. Gaps over 15% are flagged as suspicious. Tests: tests/e2e/verdict.test.js.

## Faster refresh and live scores

- **Faster refresh:** the downloads now only look at months from the last saved game onward (they used to re-read the whole season), and NBA and football run side by side. Football predictions still take about 2 minutes, NBA about 1.
- **Bug fixed:** the NBA step crashed whenever Utah played (ESPN calls them UTAH, Basketball-Reference UTA), which would have silently kept old NBA predictions.
- **Live scores:** the **Live** button shows games in play, finished and coming up (NBA + all football leagues), with scores and the clock. A page cannot fetch from the internet itself, so scores come from `live.json`, written by `python -m betsuggester.live` (about 3 seconds) and republished. **Update scores** starts a quick run (scheduled task "Live scores for Prop Finder", no timer; 2-minute cooldown). The page re-reads the file every 45 seconds while Live is open, and the daily refresh also writes it. Tests: `tests/e2e/live.test.js`.
