# Projexian SAM.gov package downloader

Runs every morning on GitHub's free servers. It finds new federal solicitations Projexian can bid
(small business set-aside or unrestricted, due 7+ days out, in Projexian's service NAICS codes),
downloads every attached file, and saves them here:

- `packages/<due date> - <solicitation #> - <title>/` holds the files plus `notice.json` (agency, place, set-aside, contracting officer contacts)
- `packages/INDEX.md` lists what was added each day

It searches every registered NAICS code (`naics_codes.py`) plus these PSC codes, because agencies
often file service work under a NAICS code Projexian isn't registered for: S201 custodial, S208
landscaping, S205 trash, S222 waste treatment, S299 housekeeping, S216 facilities support,
W099/W045/W054 equipment lease and rental, V112/V129 moving.

Each `notice.json` says where the documents are:
- `docs`: `in_repo`, or the system that holds them, such as `PIEE (not in repo)`,
  `DIBBS (not in repo)`, `NECO (not in repo)`, `FedConnect (not in repo)`,
  `SAM.gov controlled access (not in repo)` or `none posted`
- `links`: the links SAM.gov gives for those systems
- `files`: each downloaded file and its result
- `psc`, `naics`, `foundBy` (which search found it)

If a run fails or times out, the workflow opens or updates a GitHub issue titled
"Daily SAM.gov run failed". One bad notice no longer stops the run; it is listed in the run summary.

Run it by hand: **Actions** tab → **Daily SAM.gov packages** → **Run workflow**.

It also saves **Sources Sought / RFI** notices (market research the government posts months before a contract) under `sources-sought/`, with the notice text in `notice.json` and any attachments. `sources-sought/INDEX.md` lists them.
