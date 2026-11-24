# Bet Suggester

Personal tool that estimates the probability of NBA player props hitting (points, rebounds, assists,
threes), then lets you type in a bookmaker's line and odds to see if a bet is worth taking.

Two sections planned:
1. **Best bets** – props where the model's probability beats the odds you enter.
2. **Most probable bets** – props most likely to hit, filtered to odds above a minimum you set.

## Status
- [x] NBA data downloader (Basketball-Reference, cached, rate-limited)
- [x] Points model + back-test (src/betsuggester/backtest.py); rebounds, assists, threes next
- [ ] Web page for iPhone (two sections)
- [ ] Football, American football, tennis

## Run the data download
```
pip install -r requirements.txt
PYTHONPATH=src python -m betsuggester.ingest 2027   # 2027 = 2026-27 season
PYTHONPATH=src python -m pytest -q tests
```
Safe to re-run daily: only new games are fetched. Data lands in `data/` (not committed).

This tool only suggests; it doesn't place bets. Probabilities are model estimates, not guarantees.
