# Projexian SAM.gov package downloader

Runs every morning on GitHub's free servers. It finds new federal solicitations Projexian can bid
(small business set-aside or unrestricted, due 12+ days out, in Projexian's service NAICS codes),
downloads every attached file, and saves them here:

- `packages/<due date> - <solicitation #> - <title>/` holds the files plus `notice.json` (agency, place, set-aside, contracting officer contacts)
- `packages/INDEX.md` lists what was added each day

Run it by hand: **Actions** tab → **Daily SAM.gov packages** → **Run workflow**.
