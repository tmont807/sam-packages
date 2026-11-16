---
name: brief
description: Projexian's daily summary inside Claude - new federal bids worth pursuing, bid deadlines, commercial prospect replies from Gmail, and what to do today. Use when the user asks for the brief, a summary, "what's going on", or "what should I do today".
---

# Projexian brief

Give the summary in chat. Do not email it.

1. Get today's data: `git pull --rebase -q` (skip if it fails; say the data may be a day old).
2. Gmail replies, if the Gmail tools are available:
   - Run `python leads/replies.py queries --days 14`. If it prints nothing to search, skip to step 3.
   - Run each printed query with Gmail `search_threads`. Collect every message that is not from
     the user's own address as `{"id", "from", "subject", "snippet", "date"}`; for a thread with
     more than the preview shows, read it with `get_thread`.
   - Write them to a JSON file in the scratchpad and run `python leads/replies.py apply <file>`.
     It marks replies, opt-outs and bounces. Opt-outs are honored automatically.
3. Run `python bid-desk/brief.py --days 2`.
4. Summarize in this order, short, plain language, no tables wider than 5 columns:
   - **Replies waiting on you** (most urgent): who, what they said, and one suggested next step each.
     Offer to draft responses; create Gmail drafts only if the user says yes, and never send.
   - **Deadlines**: active federal bids due within 5 days, and any with subs asked but no quote.
   - **New federal bids**: the best 3 to 5, one line each with why.
   - **Commercial pipeline**: prospects ready to email, sent, replies, meetings, wins.
   - **Today**: 3 concrete actions at most.
5. If replies.py changed any lead files, commit them (`git add leads/data leads/optout.txt
   leads/replies_seen.txt`) and push only if the user agrees.
