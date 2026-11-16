#!/usr/bin/env python3
"""Turn prospect lists into cold-email batches and track replies.

  python leads/outreach.py batch kansas-city-mo --size 50          next 50 best uncontacted, as CSV
  python leads/outreach.py batch all --size 200 --types hotel,medical
  python leads/outreach.py preview kansas-city-mo                  print the first 3 emails
  python leads/outreach.py mark kansas-city-mo n123456 replied "wants janitorial quote"
  python leads/outreach.py optout someone@business.com             never email again (all cities)
  python leads/outreach.py stats

The batch CSV (email, first_name, company, subject, body, ...) imports into any sending tool or
mail merge. Prospects in a batch are marked "sent", so the next batch picks up new ones.

Commercial email law (CAN-SPAM): each email must carry your real postal address, a working
opt-out, an honest subject and From line. Fill in leads/config.json; batch refuses to run
without the address. Honor opt-outs within 10 business days: run `optout` for each one.
"""
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import BUYERS, SERVICES  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "batches")
CONFIG = os.path.join(HERE, "config.json")
OPTOUT = os.path.join(HERE, "optout.txt")
STAGES = ["new", "sent", "replied", "meeting", "quoted", "won", "lost", "optout", "bounced"]

OPENERS = {
    "office": "Keeping an office clean, comfortable and running usually means juggling a handful of vendors.",
    "property_mgr": "Most property managers I talk to are juggling a different vendor for every building and every service.",
    "apartments": "Keeping a community looking good for residents usually means a long list of vendors to manage.",
    "hotel": "Guests notice the lobby, the parking lot and the kitchen long before they notice anything else.",
    "restaurant": "Grease traps, hoods and pests are the three things that can shut a kitchen down on short notice.",
    "medical": "Patients judge a practice by how clean it is, and the compliance side of cleaning keeps getting stricter.",
    "senior": "Residents and families notice cleanliness first, and inspectors notice the kitchen.",
    "school": "Facilities teams at schools are stretched thin, especially between terms and during snow season.",
    "worship": "Most congregations rely on a few volunteers to keep the building and grounds in shape.",
    "warehouse": "Warehouses and plants burn a lot of time coordinating cleaning, hauling and lot maintenance.",
    "retail_center": "Shoppers decide a lot about a center from the parking lot and the entrances.",
    "grocery": "Floors, pests and the parking lot are what customers notice first at a grocery store.",
    "auto": "On a car lot, clean glass and a clean lot sell cars.",
    "fitness": "Members cancel over a dirty gym faster than over almost anything else.",
    "bank": "Branches have to look sharp every day, and shredding and snow can't wait.",
    "construction": "Final cleans, portable restrooms and dumpsters are the punch-list items that hold up closeout.",
    "venue": "Every event means a cleanup crew, restrooms, security and a parking plan.",
}
SUBJECTS = ["{svc} for {company}", "Question about {company}'s {svc}", "{svc} in {city}"]


def load_config():
    try:
        c = json.load(open(CONFIG))
    except (OSError, ValueError):
        sys.exit(f"Create {CONFIG} (see config.example.json).")
    if not c.get("postal_address") or "FILL" in c["postal_address"]:
        sys.exit("leads/config.json needs your real postal_address (required by CAN-SPAM) before sending.")
    return c


def city_files(which):
    files = sorted(glob.glob(os.path.join(DATA, "*.json")))
    return files if which == "all" else [f for f in files if os.path.basename(f)[:-5] == which]


def h(email):
    """Opt-outs are stored hashed: the repo is public, and a hash still blocks a resend."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def optouts():
    try:
        return {l.strip() for l in open(OPTOUT) if l.strip()}
    except OSError:
        return set()


def compose(p, c, rnd):
    svcs = [SERVICES[s] for s in BUYERS[p["type"]][3]]
    top, more = svcs[:3], len(svcs) - 3
    company = p["name"]
    subject = rnd.choice(SUBJECTS).format(svc=top[0].capitalize(), company=company, city=p["city"])
    body = f"""Hi,

{OPENERS.get(p['type'], OPENERS['office'])}

{c['company']} gives {company} one point of contact for {top[0]}, {top[1]} and {top[2]}{f', plus {more} other services' if more > 0 else ''}, done by vetted local crews in {p['city']}. You get one vendor, one invoice, and one person to call when something is wrong.

Who handles facility vendors for {company}? If it's you, would a quick quote on {top[0]} be useful?

{c['sender_name']}
{c['company']} | {c['phone']} | {c['website']}

--
{c['company']}, {c['postal_address']}
Not the right person or not interested? Reply "remove" and we won't email you again."""
    return subject, body


def cmd_batch(a):
    c = load_config()
    which = a[0]
    size = int(a[a.index("--size") + 1]) if "--size" in a else 50
    types = a[a.index("--types") + 1].split(",") if "--types" in a else None
    blocked = optouts()
    pool = []
    for f in city_files(which):
        for p in json.load(open(f)):
            if p.get("status", "new") != "new" or not p.get("email") or h(p["email"]) in blocked:
                continue
            if types and p["type"] not in types:
                continue
            pool.append((p.get("score", 0), f, p))
    pool.sort(key=lambda x: -x[0])
    seen, chosen = set(), []
    for s, f, p in pool:
        if p["email"].lower() in seen:
            continue
        seen.add(p["email"].lower())
        chosen.append((f, p))
        if len(chosen) >= size:
            break
    if not chosen:
        sys.exit("No uncontacted prospects with email. Run prospects.py with --enrich to find more.")
    rnd = random.Random(dt.date.today().toordinal())
    os.makedirs(OUT, exist_ok=True)
    out, n = os.path.join(OUT, f"{dt.date.today()}-{which}.csv"), 1
    while os.path.exists(out):
        n += 1
        out = os.path.join(OUT, f"{dt.date.today()}-{which}-{n}.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["email", "company", "type", "city", "state", "phone", "subject", "body", "prospect_id", "list"])
        for f, p in chosen:
            subj, body = compose(p, c, rnd)
            w.writerow([p["email"], p["name"], p["type_label"], p["city"], p["state"], p["phone"], subj, body,
                        p["id"], os.path.basename(f)[:-5]])
    by_file = {}
    for f, p in chosen:
        by_file.setdefault(f, set()).add(p["id"])
    for f, ids in by_file.items():
        rows = json.load(open(f))
        for p in rows:
            if p["id"] in ids:
                p["status"] = "sent"
                p["sent"] = str(dt.date.today())
        json.dump(rows, open(f, "w"), indent=0)
    print(f"{len(chosen)} emails -> {os.path.relpath(out, HERE)}")
    print("Send from a separate domain (not projexian.com itself) and keep it under ~50/day per inbox at first.")


def cmd_preview(a):
    c = load_config()
    rnd = random.Random(1)
    rows = [p for f in city_files(a[0]) for p in json.load(open(f)) if p.get("email")]
    rows.sort(key=lambda p: -p.get("score", 0))
    for p in rows[:3]:
        s, b = compose(p, c, rnd)
        print(f"To: {p['email']}\nSubject: {s}\n\n{b}\n{'=' * 70}")


def cmd_mark(a):
    which, pid, stage = a[0], a[1], a[2]
    if stage not in STAGES:
        sys.exit(f"stage must be one of {STAGES}")
    for f in city_files(which):
        rows = json.load(open(f))
        for p in rows:
            if p["id"] == pid:
                p["status"] = stage
                if a[3:]:
                    p["notes"] = (p.get("notes", "") + f" | {dt.date.today()}: " + " ".join(a[3:])).strip(" |")
                json.dump(rows, open(f, "w"), indent=0)
                print(f"{p['name']} -> {stage}")
                if stage == "optout" and p.get("email"):
                    cmd_optout([p["email"]])
                return
    sys.exit(f"{pid} not found in {which}")


def cmd_optout(a):
    blocked = optouts()
    with open(OPTOUT, "a") as f:
        for e in a:
            if h(e) not in blocked:
                f.write(h(e) + "\n")
    for path in city_files("all"):
        rows = json.load(open(path))
        hit = False
        for p in rows:
            if p.get("email", "").lower() in {e.lower() for e in a}:
                p["status"], hit = "optout", True
        if hit:
            json.dump(rows, open(path, "w"), indent=0)
    print(f"opted out: {', '.join(a)}")


def cmd_stats(a):
    tot = {}
    print(f"{'List':<24} {'Prospects':>9} {'Email':>6}  " + " ".join(f"{s:>8}" for s in STAGES[1:]))
    for f in city_files("all"):
        rows = json.load(open(f))
        n = {s: sum(1 for p in rows if p.get("status") == s) for s in STAGES}
        e = sum(1 for p in rows if p.get("email"))
        for k, v in n.items():
            tot[k] = tot.get(k, 0) + v
        print(f"{os.path.basename(f)[:-5]:<24} {len(rows):>9} {e:>6}  " + " ".join(f"{n[s]:>8}" for s in STAGES[1:]))
    sent = sum(tot.get(s, 0) for s in STAGES[1:7])
    if sent:
        print(f"\nReply rate: {sum(tot.get(s, 0) for s in STAGES[2:7]) / sent:.1%} of {sent} sent")


CMDS = {"batch": cmd_batch, "preview": cmd_preview, "mark": cmd_mark, "optout": cmd_optout, "stats": cmd_stats}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        sys.exit(__doc__)
    CMDS[sys.argv[1]](sys.argv[2:])
