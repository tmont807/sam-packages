# sam-packages

Public repo. Feeds Projexian LLC's federal contract agents, which cannot reach SAM.gov
directly, so the daily run must stay reliable. Projexian primes jobs and subcontracts 100% of
the work; it holds no bonding, trade licenses or 8(a)/HUBZone/SDVOSB/WOSB certifications.

## Rules for Claude Code here
- Code and repo work only. Do not send email, reply to subcontractors, GCs or contracting
  officers, edit the CRM, or change scheduled agents. The Claude chat app owns those.
- Do not put personal contact details, phone numbers or anything private in this repo.
- Keep the folder naming exactly: `packages/<due YYYY-MM-DD> - <solicitation #> - <title>/`
  (same for `sources-sought/`). Agents clone with
  `git clone --depth 1 --filter=blob:none --sparse` and
  `git sparse-checkout set --no-cone '*<solicitation #>*'`.
- Keep `notice.json` fields backward compatible: add fields, don't rename or remove them.

## Layout
- `fetch_sam_packages.py`: daily downloader (`.github/workflows/daily.yml`). Searches every
  NAICS in `naics_codes.py` plus the PSC list at the top of the script. Records `docs`
  (where the documents are) and `links` for PIEE, DIBBS, NECO and similar systems.
- `build_feed.py`, `build_awards.py`: data for projexian.com (`feed.json`, `awards.json`).
- `bid-desk/`, `leads/`: on the `bid-desk` branch until merged.
- A failed or timed-out daily run opens a GitHub issue "Daily SAM.gov run failed".
