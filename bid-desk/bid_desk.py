#!/usr/bin/env python3
"""Bid desk: turns the downloaded SAM.gov packages into a ranked bid list and tracks each pursuit.

The prime/sub model only makes money on bids that are (1) a service a local sub can perform,
(2) open to a plain small business, (3) far enough out to get a sub quote, and (4) sized right.
This scores every open package on those four things, shows likely incumbents and price anchors
from awards.json, and keeps a pipeline (pursuing -> subs asked -> quoted -> submitted -> won/lost).

Usage (run from the sam-packages repo root):
  python bid-desk/bid_desk.py triage [--all] [--top 40]   rank open packages, write bid-desk/BOARD.md
  python bid-desk/bid_desk.py show SOL                    details, incumbents, pipeline record
  python bid-desk/bid_desk.py status SOL pursuing|pass|subs_asked|quoted|submitted|won|lost [note]
  python bid-desk/bid_desk.py sub SOL "Company" email@x.com [phone]
  python bid-desk/bid_desk.py quote SOL "Company" 48000 [--markup 0.18]
  python bid-desk/bid_desk.py rfq SOL                     sub request-for-quote email draft
  python bid-desk/bid_desk.py pipeline                    everything not new/pass, by stage
Standard library only.
"""
import datetime as dt
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PIPE = os.path.join(HERE, "pipeline.json")
BOARD = os.path.join(HERE, "BOARD.md")
TODAY = dt.date.today()
STAGES = ["new", "pursuing", "subs_asked", "quoted", "submitted", "won", "lost", "pass"]
DEFAULT_MARKUP = 0.18

sys.path.insert(0, ROOT)
try:
    from naics_codes import NAICS_TITLES
except ImportError:
    NAICS_TITLES = {}

# Services a local subcontractor performs on site: the core of a prime/sub model.
SUBBABLE = ("5617", "5621", "5629", "562991", "5612", "5616", "532", "811192", "811310",
            "812332", "812930", "722310", "115310", "561990", "561210")
# Bonding, licensing and self-performance usually required; hard to sub 100%.
CONSTRUCTION = ("236", "237", "238")
# Product supply: thin margins, sourcing game, not this business.
PRODUCTS = ("332", "334", "335", "337", "339", "423")
# Set-asides a plain small business can bid. Anything else (SDVOSB, 8(a), WOSB, HUBZone) needs
# that certification.
OPEN_SETASIDES = {"SBA", "SBP", "UNRESTRICTED", "NONE", ""}
# Titles that signal a large multi-function or multi-award vehicle a new prime cannot sub out whole.
BIG_WORDS = ("BASE OPERATION", "BOSC", "IDIQ", "MATOC", "SATOC", "AFCAP", "ENTERPRISE", "MULTIPLE AWARD")
# Titles that signal a course, study or staffing job miscoded under a service NAICS.
NOT_SITE_WORK = ("COURSE", "TRAINING", "STUDY", "CONSULT", "SOFTWARE", "LICENSE")
GENERIC = {"SERVICES", "SERVICE", "MAINTENANCE", "REPAIR", "SUPPORT", "CONTRACT", "PROVIDE",
           "BASE", "ANNUAL", "FACILITY", "FACILITIES", "OPTION", "PERIOD"}


def naics_lane(n):
    n = n or ""
    if n.startswith(SUBBABLE):
        return "service"
    if n.startswith(CONSTRUCTION):
        return "construction"
    if n.startswith(PRODUCTS):
        return "product"
    return "professional"


def load_packages():
    out = {}
    for path in glob.glob(os.path.join(ROOT, "packages", "*", "notice.json")):
        try:
            d = json.load(open(path))
        except (OSError, ValueError):
            continue
        sol = d.get("solicitationNumber") or d.get("noticeId")
        try:
            due = dt.date.fromisoformat((d.get("due") or "")[:10])
        except ValueError:
            due = None
        d["_due"] = due
        d["_dir"] = os.path.dirname(path)
        prev = out.get(sol)
        if not prev or (d.get("savedAt", "") > prev.get("savedAt", "")):
            out[sol] = d
    return out


def load_awards():
    p = os.path.join(ROOT, "awards.json")
    try:
        a = json.load(open(p))
    except (OSError, ValueError):
        return {}, []
    return a.get("past", {}), a.get("recompetes", [])


def anchors(d, past, recompetes):
    """Comparable past awards (same state + NAICS) and expiring contracts that look like this one."""
    st, n = d.get("state") or "", d.get("naics") or ""
    if not st:
        return [], []
    comps = past.get(f"{st}|{n}", [])
    words = {w for w in (d.get("title") or "").upper().replace("--", " ").split()
             if len(w) > 4 and w not in GENERIC}
    rec = [r for r in recompetes if r.get("n") == n and r.get("st") == st
           and words & set((r.get("desc") or "").upper().split())]
    return comps, rec


def score(d, past, recompetes):
    """0-100 bid-fit score plus the reasons, so a 'pass' is explainable."""
    why, s = [], 35
    sa = (d.get("setAside") or "").upper()
    if sa not in OPEN_SETASIDES:
        return 0, [f"set-aside {sa} needs certification"]
    lane = naics_lane(d.get("naics"))
    s += {"service": 25, "professional": 0, "construction": -15, "product": -30}[lane]
    why.append(f"{lane} lane")
    title = (d.get("title") or "").upper()
    if any(w in title for w in BIG_WORDS):
        s -= 25
        why.append("large multi-function/multi-award vehicle")
    if lane == "service" and any(w in title for w in NOT_SITE_WORK):
        s -= 20
        why.append("title reads as non-site work despite NAICS")
    if sa in ("SBA", "SBP"):
        s += 10
        why.append("small-business set-aside")
    due = d["_due"]
    if due:
        days = (due - TODAY).days
        if days < 0:
            return 0, ["past due"]
        if days < 5:
            s -= 30
            why.append(f"{days}d left, too short for a sub quote")
        elif days <= 10:
            s += 10
            why.append(f"{days}d left, move now")
        elif days <= 21:
            s += 15
            why.append(f"{days}d left")
        else:
            why.append(f"{days}d left")
    if d.get("state"):
        s += 5
    else:
        s -= 10
        why.append("no place of performance in notice, read the SOW")
    comps, rec = anchors(d, past, recompetes)
    if comps:
        med = sorted(c["amt"] for c in comps)[len(comps) // 2]
        if med > 5_000_000:
            s -= 15
            why.append(f"comparable awards are large (median ${med:,.0f})")
        elif med < 1_000_000:
            s += 10
            why.append(f"comparable awards right-sized (median ${med:,.0f})")
    if len(d.get("files", [])) >= 2:
        s += 5
    else:
        why.append("thin package")
    if rec:
        why.append(f"possible recompete of {rec[0]['r']}")
    return max(0, min(100, s)), why


def load_pipe():
    try:
        return json.load(open(PIPE))
    except (OSError, ValueError):
        return {}


def save_pipe(p):
    json.dump(p, open(PIPE, "w"), indent=1, sort_keys=True)


def rec_for(pipe, sol):
    return pipe.setdefault(sol, {"status": "new", "notes": [], "subs": []})


def cmd_triage(args):
    pk, (past, rc), pipe = load_packages(), load_awards(), load_pipe()
    top = int(args[args.index("--top") + 1]) if "--top" in args else 40
    rows = []
    for sol, d in pk.items():
        sc, why = score(d, past, rc)
        st = pipe.get(sol, {}).get("status", "new")
        if sc == 0 and "--all" not in args:
            continue
        rows.append((sc, sol, d, why, st))
    rows.sort(key=lambda r: (-r[0], r[2]["_due"] or dt.date.max))
    lanes = {}
    for _, _, d, _, _ in rows:
        lanes[naics_lane(d.get("naics"))] = lanes.get(naics_lane(d.get("naics")), 0) + 1
    lines = [f"# Bid board, {TODAY}", "",
             f"{len(rows)} biddable open packages out of {len(pk)} downloaded. By lane: "
             + ", ".join(f"{k} {v}" for k, v in sorted(lanes.items(), key=lambda x: -x[1])), "",
             "| Score | Due | Solicitation | Title | Where | Set-aside | Stage | Why |",
             "|---|---|---|---|---|---|---|---|"]
    for sc, sol, d, why, st in rows[:top]:
        where = ", ".join(x for x in (d.get("city"), d.get("state")) if x) or "?"
        lines.append(f"| {sc} | {d['_due']} | {sol} | {(d.get('title') or '')[:60]} | {where} | "
                     f"{d.get('setAside')} | {st} | {'; '.join(why)} |")
    open(BOARD, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))
    for sc, sol, d, why, st in rows[:top]:
        print(f"{sc:>3}  {d['_due']}  {sol:<24} {(d.get('title') or '')[:52]:<52} {d.get('state') or '?':<3} {st}")
    print(f"\nWrote {os.path.relpath(BOARD, ROOT)}")


def find(sol):
    pk = load_packages()
    if sol not in pk:
        hits = [k for k in pk if sol.lower() in k.lower()]
        if len(hits) != 1:
            sys.exit(f"No single package matches {sol!r}" + (f": {hits[:8]}" if hits else ""))
        sol = hits[0]
    return sol, pk[sol]


def cmd_show(args):
    sol, d = find(args[0])
    past, rc = load_awards()
    sc, why = score(d, past, rc)
    comps, rec = anchors(d, past, rc)
    print(f"{sol}  {d.get('title')}\n  agency: {d.get('agency')}\n  NAICS {d.get('naics')} "
          f"({NAICS_TITLES.get(d.get('naics'), '?')}), set-aside {d.get('setAside')}, due {d['_due']}, "
          f"{d.get('city') or ''} {d.get('state') or ''}\n  score {sc}: {'; '.join(why)}")
    for c in d.get("contacts", []):
        print(f"  CO: {c.get('name')} {c.get('email')} {c.get('phone')}")
    print(f"  files ({os.path.relpath(d['_dir'], ROOT)}): " + ", ".join(f['name'] for f in d.get("files", [])))
    if comps:
        print("  comparable awards, same state + NAICS:")
        for c in sorted(comps, key=lambda c: c["amt"])[:6]:
            print(f"    ${c['amt']:>12,.0f}  {c['r'][:40]:<40} {c.get('desc', '')[:60]}")
    for r in rec[:3]:
        print(f"  possible incumbent: {r['r']}  ${r['amt']:,.0f}  ends {r['end']}  {r['desc'][:60]}")
    p = load_pipe().get(sol)
    if p:
        print(f"  pipeline: {p['status']}")
        for s in p["subs"]:
            q = f"  quote ${s['quote']:,.0f} -> bid ${s['bid']:,.0f}" if s.get("quote") else ""
            print(f"    sub: {s['name']} {s.get('email', '')} {s.get('phone', '')}{q}")
        for n in p["notes"]:
            print(f"    {n}")


def cmd_status(args):
    sol, _ = find(args[0])
    if args[1] not in STAGES:
        sys.exit(f"stage must be one of {STAGES}")
    pipe = load_pipe()
    r = rec_for(pipe, sol)
    r["status"] = args[1]
    r["notes"].append(f"{TODAY} {args[1]}" + (f": {' '.join(args[2:])}" if args[2:] else ""))
    save_pipe(pipe)
    print(f"{sol} -> {args[1]}")


def cmd_sub(args):
    sol, _ = find(args[0])
    pipe = load_pipe()
    r = rec_for(pipe, sol)
    r["subs"].append({"name": args[1], "email": args[2] if len(args) > 2 else "",
                      "phone": args[3] if len(args) > 3 else ""})
    if r["status"] in ("new", "pursuing"):
        r["status"] = "subs_asked"
    save_pipe(pipe)
    print(f"{sol}: {len(r['subs'])} sub(s)")


def cmd_quote(args):
    sol, _ = find(args[0])
    markup = float(args[args.index("--markup") + 1]) if "--markup" in args else DEFAULT_MARKUP
    amt = float(args[2].replace(",", "").replace("$", ""))
    pipe = load_pipe()
    r = rec_for(pipe, sol)
    sub = next((s for s in r["subs"] if s["name"].lower() == args[1].lower()), None)
    if not sub:
        sub = {"name": args[1]}
        r["subs"].append(sub)
    sub["quote"], sub["bid"] = amt, round(amt * (1 + markup), 2)
    r["status"] = "quoted"
    save_pipe(pipe)
    print(f"{sol}: {args[1]} quoted ${amt:,.0f}. At {markup:.0%} markup bid ${sub['bid']:,.0f}, "
          f"gross margin ${sub['bid'] - amt:,.0f} ({(sub['bid'] - amt) / sub['bid']:.1%} of price).")
    quotes = sorted(s["quote"] for s in r["subs"] if s.get("quote"))
    if len(quotes) > 1:
        print(f"  {len(quotes)} quotes: low ${quotes[0]:,.0f}, high ${quotes[-1]:,.0f}")


def cmd_rfq(args):
    sol, d = find(args[0])
    due = d["_due"]
    ask = due - dt.timedelta(days=max(2, min(5, ((due - TODAY).days) // 3))) if due else None
    where = ", ".join(x for x in (d.get("city"), d.get("state")) if x) or "[location from SOW]"
    files = "\n".join(f"  - {f['name']}" for f in d.get("files", []))
    title = d.get("title") or ""
    # Tyler's sub-email rules: this opening, under ~200 words, documents attached to this email,
    # no portal links, no calls or meetings offered, never our pricing or markup.
    print(f"""Subject: Quote request: {title} - {where} (due {ask:%b %-d})

Hi [Company] team,

My name is Tyler Montgomery with Projexian. We're preparing a quote for {title} for
{(d.get('agency') or '').split('>')[-1].strip() or 'a federal agency'} in {where}, and we're looking for a
local small business to perform the work as our subcontractor.

Attached are the solicitation documents:
{files}

If you'd like to bid, please send by {ask:%A, %B %-d}:
1. Your price for the full scope, using the attached price schedule (each option year)
2. Confirmation you can meet the attached wage determination
3. A recent comparable job and your certificate of insurance

Thank you,
Tyler Montgomery
Projexian LLC

[Attach every file above. Send only when Tyler says "send", paced per his rules.]""")



def cmd_pipeline(args):
    pipe, pk = load_pipe(), load_packages()
    for stage in STAGES[1:-1]:
        rows = [(s, r) for s, r in pipe.items() if r["status"] == stage]
        if not rows:
            continue
        print(f"\n== {stage} ({len(rows)})")
        for s, r in sorted(rows, key=lambda x: pk.get(x[0], {}).get("_due") or dt.date.max):
            d = pk.get(s, {})
            q = [x["bid"] for x in r["subs"] if x.get("bid")]
            print(f"  {d.get('_due')}  {s:<24} {(d.get('title') or '')[:50]:<50} subs {len(r['subs'])}"
                  + (f"  bid ${min(q):,.0f}" if q else ""))
    won = [r for r in pipe.values() if r["status"] == "won"]
    sub = [r for r in pipe.values() if r["status"] in ("submitted", "won", "lost")]
    if sub:
        print(f"\nWin rate: {len(won)}/{len(sub)} decided or submitted bids")


CMDS = {"triage": cmd_triage, "show": cmd_show, "status": cmd_status, "sub": cmd_sub,
        "quote": cmd_quote, "rfq": cmd_rfq, "pipeline": cmd_pipeline}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        sys.exit(__doc__)
    CMDS[sys.argv[1]](sys.argv[2:])
