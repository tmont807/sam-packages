#!/usr/bin/env python3
"""Government bid lead reports: Projexian's lead generation product.

For a customer's trade and states, one report with:
  1. Open bids they can quote now (SAM.gov, from today's feed.json)
  2. Early notices: sources sought / RFIs, months before the bid (feed.json)
  3. Contracts expiring in the next 18 months: who holds them, value, end date (USAspending)
  4. Who wins this work in their states: top contract holders (USAspending)

  python leadgen/report.py --trade janitorial --states IL,WI,IN --customer "Acme Cleaning"
  python leadgen/report.py --trade landscaping --states TX --months 12
  python leadgen/report.py --list                      trades available

Writes leadgen/out/<date>-<trade>-<states>.html (print to PDF from a browser) and a .csv of every
lead. leadgen/out/ is not committed: customer reports stay private. Standard library only.
"""
import csv
import datetime as dt
import html
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")
API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

# trade: (label, NAICS codes, PSC codes). NAICS outside Projexian's registered list still work for
# expiring contracts and winners; open bids and early notices come from the daily feed, which
# covers Projexian's registered NAICS.
TRADES = {
    "janitorial": ("Janitorial and custodial", ["561720"], ["S201"]),
    "landscaping": ("Landscaping and grounds", ["561730"], ["S208"]),
    "snow": ("Snow removal and building services", ["561790"], []),
    "pest": ("Pest control", ["561710"], ["S207"]),
    "waste": ("Trash, recycling and waste hauling", ["562111", "562119", "562920"], ["S205"]),
    "septic": ("Portable restrooms, septic and pumping", ["562991", "562998"], ["S222"]),
    "facilities": ("Facilities support and O&M", ["561210"], ["S216"]),
    "security": ("Security guards", ["561612"], ["S206"]),
    "hvac": ("HVAC and plumbing", ["238220"], []),
    "electrical": ("Electrical", ["238210"], []),
    "painting": ("Painting", ["238320"], []),
    "roofing": ("Roofing", ["238160"], []),
    "flooring": ("Flooring and carpet care", ["238330", "561740"], []),
    "construction": ("General building construction", ["236220", "236118"], []),
    "sitework": ("Site prep, paving and civil", ["238910", "237310", "237990"], []),
    "moving": ("Moving and freight", ["484210", "484110", "484121"], ["V112", "V129"]),
    "rental": ("Equipment rental", ["532490", "532412", "532120"], ["W099", "W045", "W054"]),
    "it": ("IT services", ["541512", "541519"], []),
    "staffing": ("Staffing and admin support", ["561320", "561110"], []),
    "training": ("Training", ["611430"], []),
    "food": ("Food service", ["722310"], []),
    "laundry": ("Laundry", ["812332"], []),
}

STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
               "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
               "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
               "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
               "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
               "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
               "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
               "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
               "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
               "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
               "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
               "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands"}
SET_ASIDES = {"SBA": "Small business", "SBP": "Small business (partial)", "SDVOSBC": "SDVOSB", "SDVOSBS": "SDVOSB",
              "8A": "8(a)", "8AN": "8(a) sole source", "HZC": "HUBZone", "HZS": "HUBZone", "WOSB": "WOSB",
              "EDWOSB": "EDWOSB", "ISBEE": "Indian small business", "VSA": "Veteran-owned", "NONE": "Open to all",
              "": "Open to all"}


def post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "ProjexianLeads/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def awards(naics, psc, state, years, sort, pages):
    today = dt.date.today()
    f = {"award_type_codes": ["A", "B", "C", "D"],
         "place_of_performance_locations": [{"country": "USA", "state": state}],
         "time_period": [{"start_date": (today - dt.timedelta(days=365 * years)).isoformat(),
                          "end_date": today.isoformat()}]}
    if naics:
        f["naics_codes"] = {"require": naics}
    else:
        f["psc_codes"] = {"require": [[c[0], c] for c in psc]}
    body = {"filters": f, "fields": ["Award ID", "Recipient Name", "Award Amount", "Start Date", "End Date",
                                     "Awarding Sub Agency", "Description", "NAICS"],
            "sort": sort, "order": "desc", "limit": 100, "subawards": False}
    rows = []
    for page in range(1, pages + 1):
        body["page"] = page
        res = post(body)
        rows += res.get("results", [])
        if not res.get("page_metadata", {}).get("hasNext"):
            break
        time.sleep(0.3)
    return rows


def clean_desc(s):
    s = (s or "").strip()
    for junk in ("IGF::OT::IGF", "IGF::CL::IGF", "IGF::CT::IGF", "IGF::OT::IGF "):
        s = s.replace(junk, "")
    return s.strip(" -:")[:140].capitalize()


def expiring(trade, states, months):
    _, naics, psc = TRADES[trade]
    # Contracts ending in the next ~60 days have usually been rebid already, so they aren't actionable.
    today = (dt.date.today() + dt.timedelta(days=60)).isoformat()
    horizon = (dt.date.today() + dt.timedelta(days=int(months * 30.5))).isoformat()
    out, seen = [], set()
    for st in states:
        rows = awards(naics, psc, st, 6, "End Date", 4)
        for r in rows:
            end = r.get("End Date") or ""
            if not (today <= end <= horizon) or (r.get("Award Amount") or 0) < 10000 or r["Award ID"] in seen:
                continue
            seen.add(r["Award ID"])
            out.append({"state": st, "end": end, "holder": (r.get("Recipient Name") or "").title(),
                        "value": float(r.get("Award Amount") or 0), "agency": r.get("Awarding Sub Agency") or "",
                        "what": clean_desc(r.get("Description")), "award_id": r["Award ID"],
                        "link": f"https://www.usaspending.gov/award/{r.get('generated_internal_id', '')}"})
    return sorted(out, key=lambda x: x["end"])


def winners(trade, states):
    _, naics, psc = TRADES[trade]
    tot = {}
    for st in states:
        for r in awards(naics, psc, st, 3, "Award Amount", 3):
            name = (r.get("Recipient Name") or "").title()
            w = tot.setdefault(name, {"holder": name, "value": 0.0, "awards": 0, "states": set()})
            w["value"] += float(r.get("Award Amount") or 0)
            w["awards"] += 1
            w["states"].add(st)
    rows = sorted(tot.values(), key=lambda w: -w["value"])[:15]
    for w in rows:
        w["states"] = ", ".join(sorted(w["states"]))
    return rows


def feed_items(trade, states):
    _, naics, _ = TRADES[trade]
    try:
        feed = json.load(open(os.path.join(ROOT, "feed.json")))
    except (OSError, ValueError):
        return [], [], ""
    today = dt.date.today().isoformat()
    hits = [i for i in feed["items"] if i.get("n") in naics and i.get("s") in states and (i.get("due") or "") >= today]
    rows = [{"kind": i["k"], "due": i.get("due", ""), "title": i.get("t", ""), "agency": i.get("a", ""),
             "place": ", ".join(x for x in (i.get("c"), i.get("s")) if x), "set_aside": SET_ASIDES.get(i.get("sa", ""), i.get("sa", "")),
             "number": i.get("sol", ""), "posted": i.get("posted", ""), "summary": (i.get("d") or "")[:260],
             "link": f"https://sam.gov/opp/{i['id']}/view"} for i in hits]
    bids = sorted([r for r in rows if r["kind"] == "sol"], key=lambda r: r["due"])
    early = sorted([r for r in rows if r["kind"] == "ss"], key=lambda r: r["due"])
    return bids, early, feed.get("updated", "")[:10]


def money(v):
    return f"${v / 1e6:,.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K" if v >= 1e3 else f"${v:,.0f}"


def fdate(s):
    try:
        return dt.date.fromisoformat(s[:10]).strftime("%b %-d, %Y")
    except ValueError:
        return s


CSS = """
:root{--ink:#14181f;--muted:#5d6673;--line:#e3e0d8;--bg:#fbfaf7;--card:#fff;--accent:#8a6a2f;--accent-soft:#f3ecdf}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#ece9e2;--muted:#a3a9b3;--line:#2c313a;--bg:#12151a;--card:#181c22;--accent:#d2b273;--accent-soft:#2a2519}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "IBM Plex Sans",system-ui,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:40px 24px 64px}
header{border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:28px}
.brand{letter-spacing:.18em;text-transform:uppercase;font-size:12px;color:var(--accent);font-weight:600}
h1{font-family:"Cormorant Garamond",Georgia,serif;font-weight:500;font-size:clamp(30px,4vw,44px);line-height:1.1;margin:10px 0 8px}
.sub{color:var(--muted);margin:0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:24px 0 8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.stat b{display:block;font-family:"Cormorant Garamond",Georgia,serif;font-size:34px;font-weight:500;line-height:1}
.stat span{color:var(--muted);font-size:13px}
h2{font-family:"Cormorant Garamond",Georgia,serif;font-weight:500;font-size:28px;margin:44px 0 4px}
.why{color:var(--muted);margin:0 0 14px;max-width:760px}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em;background:var(--accent-soft)}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
td.nowrap{white-space:nowrap}a{color:var(--accent)}.small{color:var(--muted);font-size:12.5px}
.empty{padding:16px;color:var(--muted)}footer{margin-top:48px;border-top:1px solid var(--line);padding-top:18px;color:var(--muted);font-size:12.5px}
@media print{body{background:#fff;color:#000}.tbl{border-color:#ccc}a{color:#000;text-decoration:none}h2{break-after:avoid}tr{break-inside:avoid}}
"""


def table(cols, rows, empty):
    if not rows:
        return f'<div class="tbl"><div class="empty">{empty}</div></div>'
    head = "".join(f"<th>{c}</th>" for c, _ in cols)
    body = "".join("<tr>" + "".join(f(r) for _, f in cols) + "</tr>" for r in rows)
    return f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def td(v, cls=""):
    return f'<td class="{cls}">{v}</td>'


def e(s):
    return html.escape(str(s or ""))


def build(trade, states, months, customer):
    label = TRADES[trade][0]
    print(f"{label} in {', '.join(states)}: open bids and early notices from the feed...")
    bids, early, feed_day = feed_items(trade, states)
    print("expiring contracts from USAspending...")
    exp = expiring(trade, states, months)
    print("top contract holders...")
    win = winners(trade, states)
    exp_value = sum(x["value"] for x in exp)
    where = ", ".join(STATE_NAMES.get(s, s) for s in states)
    today = dt.date.today()

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(label)} Leads</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">
<header><div class="brand">Projexian · Opportunity Intelligence</div>
<h1>{e(label)} government leads<br>{e(where)}</h1>
<p class="sub">{"Prepared for " + e(customer) + " · " if customer else ""}{today:%B %-d, %Y}</p>
<div class="stats">
<div class="stat"><b>{len(bids)}</b><span>open bids you can quote now</span></div>
<div class="stat"><b>{len(early)}</b><span>early notices (bid comes later)</span></div>
<div class="stat"><b>{len(exp)}</b><span>contracts expiring in 2–{months} months</span></div>
<div class="stat"><b>{money(exp_value)}</b><span>value of those contracts</span></div>
</div></header>

<h2>1. Open bids</h2>
<p class="why">Federal agencies are taking quotes on these now. Open the link for the full solicitation and documents.</p>
{table([("Due", lambda r: td(fdate(r["due"]), "nowrap")), ("Opportunity", lambda r: td(f'<a href="{r["link"]}">{e(r["title"])}</a><div class="small">{e(r["number"])} · {e(r["agency"])}</div>')),
        ("Where", lambda r: td(e(r["place"]))), ("Open to", lambda r: td(e(r["set_aside"])))], bids,
       "No open bids in these states for this trade today. New bids post daily; the expiring contracts below show what is coming.")}

<h2>2. Early notices</h2>
<p class="why">Sources sought and requests for information: the agency is checking who can do the work before it writes the bid. Responding gets you on the contracting officer's list and can make the job a small-business set-aside.</p>
{table([("Respond by", lambda r: td(fdate(r["due"]), "nowrap")), ("Notice", lambda r: td(f'<a href="{r["link"]}">{e(r["title"])}</a><div class="small">{e(r["number"])} · {e(r["agency"])}</div>')),
        ("Where", lambda r: td(e(r["place"])))], early, "No early notices in these states for this trade right now.")}

<h2>3. Contracts expiring soon</h2>
<p class="why">These federal contracts end 2 to {months} months from now, so the agency will bid them again, usually 2 to 6 months before the end date. Each line shows who holds the work today and what it is worth. Contracts with option years may run past the end date shown.</p>
{table([("Ends", lambda r: td(fdate(r["end"]), "nowrap")), ("Work", lambda r: td(f'{e(r["what"]) or "—"}<div class="small">{e(r["agency"])} · {e(r["state"])}</div>')),
        ("Current holder", lambda r: td(e(r["holder"]))), ("Value", lambda r: td(money(r["value"]), "num")),
        ("Record", lambda r: td(f'<a href="{r["link"]}">{e(r["award_id"])}</a>', "small"))], exp,
       "No contracts in this trade end within the window in these states.")}

<h2>4. Who wins this work</h2>
<p class="why">The companies with the most federal {e(label.lower())} work in these states over the last 3 years: your competitors, and possible teaming partners.</p>
{table([("Company", lambda r: td(e(r["holder"]))), ("Contracts", lambda r: td(r["awards"], "num")),
        ("Total value", lambda r: td(money(r["value"]), "num")), ("States", lambda r: td(e(r["states"])))], win, "No awards found.")}

<footer>Sources: SAM.gov contract opportunities{f" (as of {fdate(feed_day)})" if feed_day else ""} and USAspending.gov award data, public U.S. government records.
Verify dates and requirements in the official solicitation before bidding. © {today.year} Projexian LLC · projexian.com</footer>
</div></body></html>"""

    os.makedirs(OUT, exist_ok=True)
    base = os.path.join(OUT, f"{today}-{trade}-{'-'.join(s.lower() for s in states)}")
    open(base + ".html", "w").write(doc)
    with open(base + ".csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "date", "title_or_work", "number_or_award", "agency", "place", "set_aside_or_holder", "value", "link"])
        for r in bids:
            w.writerow(["open bid", r["due"], r["title"], r["number"], r["agency"], r["place"], r["set_aside"], "", r["link"]])
        for r in early:
            w.writerow(["early notice", r["due"], r["title"], r["number"], r["agency"], r["place"], r["set_aside"], "", r["link"]])
        for r in exp:
            w.writerow(["expiring contract", r["end"], r["what"], r["award_id"], r["agency"], r["state"], r["holder"], round(r["value"]), r["link"]])
    print(f"\n{len(bids)} open bids, {len(early)} early notices, {len(exp)} expiring ({money(exp_value)}), "
          f"{len(win)} top holders\n-> {os.path.relpath(base, ROOT)}.html and .csv")
    return base + ".html"


def main(a):
    if "--list" in a or not a:
        for k, (label, n, p) in TRADES.items():
            print(f"{k:<13} {label}  (NAICS {', '.join(n)}{'; PSC ' + ', '.join(p) if p else ''})")
        if not a:
            print(__doc__)
        return
    opt = lambda k, v: a[a.index(k) + 1] if k in a else v  # noqa: E731
    trade = opt("--trade", "")
    if trade not in TRADES:
        sys.exit(f"--trade must be one of: {', '.join(TRADES)}")
    states = [s.strip().upper() for s in opt("--states", "").split(",") if s.strip()]
    bad = [s for s in states if s not in STATE_NAMES]
    if not states or bad:
        sys.exit(f"--states needs 2-letter codes, e.g. IL,WI{'; unknown: ' + ', '.join(bad) if bad else ''}")
    build(trade, states, int(opt("--months", 18)), opt("--customer", ""))


if __name__ == "__main__":
    main(sys.argv[1:])
