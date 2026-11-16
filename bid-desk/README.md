# Bid desk

Turns the packages the daily bot downloads into a ranked bid list, then tracks each bid from
"pursuing" through sub quotes to submitted, won or lost. Standard library Python, no setup.

```
python bid-desk/bid_desk.py triage                 # rank open packages, writes bid-desk/BOARD.md
python bid-desk/bid_desk.py show FA449727Q0009     # details, CO contact, comparable awards, incumbent
python bid-desk/bid_desk.py rfq FA449727Q0009      # draft email asking local subs for a quote
python bid-desk/bid_desk.py status FA449727Q0009 pursuing
python bid-desk/bid_desk.py sub FA449727Q0009 "Delmarva Pumping" ops@example.com 302-555-0100
python bid-desk/bid_desk.py quote FA449727Q0009 "Delmarva Pumping" 38500 --markup 0.18
python bid-desk/bid_desk.py pipeline               # every active bid by stage, plus win rate
```

Partial solicitation numbers work (`show Q0009`) when they match one package.

## How the score works (0-100)

| Factor | Effect |
|---|---|
| Set-aside needs a certification Projexian lacks (SDVOSB, 8(a), WOSB, HUBZone) | score 0 |
| Past due | score 0 |
| On-site service a local sub performs (janitorial, grounds, snow, pest, waste, pumping, rentals) | +25 |
| Construction (bonding, licensing) / product supply | -15 / -30 |
| Small-business set-aside | +10 |
| Under 5 days left | -30 |
| 11-21 days left (time to get sub quotes) | +15 |
| No place of performance in the notice | -10 |
| Comparable awards in that state + NAICS are under $1M / over $5M | +10 / -15 |
| Base-ops, IDIQ, MATOC or similar large vehicle in the title | -25 |

Every score prints its reasons, so a pass is explainable. Tune the weights in `score()`.

`pipeline.json` holds your bid records. Commit it to keep history; the daily bot never touches it.
