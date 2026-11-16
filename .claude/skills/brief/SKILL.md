---
name: brief
description: Projexian's daily summary inside Claude - new federal bids worth pursuing, bid deadlines, and what to do today (repo data only, no Gmail). Use when the user asks for the brief, a summary, "what's going on", or "what should I do today".
---

# Projexian brief

Give the summary in chat. Do not email it.

1. Get today's data: `git pull --rebase -q` (skip if it fails; say the data may be a day old).
2. Run `python bid-desk/brief.py --days 2`.
3. Summarize in this order, short, plain language, no tables wider than 5 columns:
   - **Deadlines**: active federal bids due within 5 days, and any with subs asked but no quote.
   - **New federal bids**: the best 3 to 5, one line each with why.
   - **Commercial pipeline**: prospects ready to email, sent, replies, meetings, wins.
   - **Today**: 3 concrete actions at most.

Do not read or touch Gmail, the CRM or scheduled agents from Claude Code: the Claude chat app owns
email, bids and sub outreach. This brief covers repo data only.
