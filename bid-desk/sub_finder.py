#!/usr/bin/env python3
"""Find local subcontractors for a package: companies already paid by the federal government for
the same kind of work (same NAICS) in the same state, from USAspending.gov (public, no key).

A company that already did this work for an agency nearby knows the paperwork, pays wage-determination
rates and is registered in SAM.gov, which makes it the fastest sub to get a usable quote from.

  python bid-desk/sub_finder.py SOL                  ranked list, saved to bid-desk/subs/SOL.json
  python bid-desk/sub_finder.py SOL --state MO       when the notice has no place of performance
  python bid-desk/sub_finder.py SOL --years 5 --top 15
  python bid-desk/sub_finder.py SOL --add 1,3        add picks to the bid's pipeline record

Small business matters: on a small-business set-aside the prime may pay no more than 50% of a
services contract to subs that are not small businesses (FAR 52.219-14). Large subs are flagged.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bid_desk as bd  # noqa: E402

API = "https://api.usaspending.gov/api/v2"
OUT = os.path.join(bd.HERE, "subs")
TOO_BIG = 5_000_000    # total federal work in this state+NAICS above this: a national firm, not a local sub


def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "ProjexianBidDesk/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def awards(naics, state, years, pages=3):
    today = dt.date.today()
    body = {"filters": {"award_type_codes": ["A", "B", "C", "D"], "naics_codes": {"require": [naics]},
                        "place_of_performance_locations": [{"country": "USA", "state": state}],
                        "time_period": [{"start_date": (today - dt.timedelta(days=365 * years)).isoformat(),
                                         "end_date": today.isoformat()}]},
            "fields": ["Award ID", "Recipient Name", "Recipient UEI", "recipient_id", "Award Amount",
                       "Place of Performance Zip5", "Description", "End Date", "Awarding Sub Agency"],
            "sort": "End Date", "order": "desc", "limit": 100, "subawards": False}
    rows = []
    for page in range(1, pages + 1):
        body["page"] = page
        res = call("/search/spending_by_award/", body)
        rows += res.get("results", [])
        if not res.get("page_metadata", {}).get("hasNext"):
            break
    return rows


def group(rows):
    firms = {}
    for r in rows:
        key = r.get("Recipient UEI") or r.get("Recipient Name")
        f = firms.setdefault(key, {"name": (r.get("Recipient Name") or "").title(), "uei": r.get("Recipient UEI"),
                                   "rid": r.get("recipient_id"), "awards": 0, "total": 0.0, "last": "",
                                   "zips": set(), "agencies": set(), "example": ""})
        f["awards"] += 1
        f["total"] += float(r.get("Award Amount") or 0)
        if (r.get("End Date") or "") > f["last"]:
            f["last"] = r.get("End Date") or ""
            f["example"] = (r.get("Description") or "")[:90]
        if r.get("Place of Performance Zip5"):
            f["zips"].add(r["Place of Performance Zip5"])
        if r.get("Awarding Sub Agency"):
            f["agencies"].add(r["Awarding Sub Agency"])
    return list(firms.values())


def profile(f):
    try:
        p = call(f"/recipient/{urllib.parse.quote(f['rid'])}/")
    except Exception:
        return
    loc = p.get("location") or {}
    f["address"] = ", ".join(x for x in (loc.get("address_line1"), loc.get("city_name"),
                                         loc.get("state_code"), loc.get("zip")) if x)
    f["city"], f["zip"] = (loc.get("city_name") or "").title(), loc.get("zip") or ""
    f["st"] = loc.get("state_code") or ""
    t = set(p.get("business_types") or [])
    f["small"] = "small_business" in t
    f["certs"] = [lbl for key, lbl in (("service_disabled_veteran_owned_business", "SDVOSB"),
                                       ("women_owned_small_business", "WOSB"), ("historically_underutilized_business_zone", "HUBZone"),
                                       ("8a_program_participant", "8(a)"), ("veteran_owned_business", "VOSB"))
                  if key in t]


def rank(f, place_city, state):
    s = min(f["awards"], 6) * 5                                     # repeat federal work
    s += 15 if f["last"] >= (dt.date.today() - dt.timedelta(days=540)).isoformat() else 0  # active lately
    s += 20 if f.get("small") else (-25 if "small" in f else 0)     # set-aside compliance
    s -= 30 if f["total"] > TOO_BIG else 0
    if f.get("st"):
        s += 10 if f["st"] == state else -15                        # based in-state, not just worked there
    if place_city and f.get("city", "").upper() == place_city.upper():
        s += 15
    return s


def main(a):
    if not a or a[0].startswith("-"):
        sys.exit(__doc__)
    sol, d = bd.find(a[0])
    opt = lambda k, v: a[a.index(k) + 1] if k in a else v  # noqa: E731
    state = opt("--state", d.get("state") or "").upper()
    if len(state) != 2:
        sys.exit(f"{sol} has no place of performance in the notice. Read the SOW and rerun with --state XX.")
    naics, years, top = d.get("naics"), int(opt("--years", 4)), int(opt("--top", 12))
    path = os.path.join(OUT, f"{sol}.json")

    if "--add" in a:
        saved = json.load(open(path))
        pipe = bd.load_pipe()
        r = bd.rec_for(pipe, sol)
        for i in (int(x) for x in opt("--add", "").split(",")):
            f = saved["firms"][i - 1]
            r["subs"].append({"name": f["name"], "email": "", "phone": "", "uei": f["uei"], "address": f.get("address", "")})
            print(f"added {f['name']}")
        if r["status"] in ("new", "pursuing"):
            r["status"] = "subs_asked"
        bd.save_pipe(pipe)
        return

    print(f"{sol}: {d.get('title')}\nSearching federal awards for NAICS {naics} "
          f"({bd.NAICS_TITLES.get(naics, '?')}) in {state}, last {years} years...")
    firms = group(awards(naics, state, years))
    if len(firms) < 5 and len(naics or "") == 6:
        print(f"Only {len(firms)} found; widening to NAICS {naics[:4]}xx.")
        firms = group(awards(naics[:4], state, years))
    firms.sort(key=lambda f: (-min(f["awards"], 6), -int(f["last"] >= "2025"), f["total"]))
    for f in firms[: top * 2]:
        profile(f)
    for f in firms:
        f["score"] = rank(f, d.get("city"), state)
    firms.sort(key=lambda f: -f["score"])
    firms = firms[:top]
    if not firms:
        sys.exit(f"No federal awardees for this work in {state}. Try --years 8, or a neighboring --state.")

    print(f"\n{'#':>2}  {'Company':<36} {'City':<16} {'Awards':>6} {'Total':>12}  Last     Flags")
    for i, f in enumerate(firms, 1):
        flags = []
        if "small" in f:
            flags.append("small" if f["small"] else "NOT SMALL")
        flags += f.get("certs", [])
        if f.get("st") and f["st"] != state:
            flags.append(f"based {f['st']}")
        if f["total"] > TOO_BIG:
            flags.append("national-size")
        print(f"{i:>2}  {f['name'][:36]:<36} {f.get('city', '')[:16]:<16} {f['awards']:>6} "
              f"${f['total']:>11,.0f}  {f['last'][:7]}  {' '.join(flags)}")
    print("\nContact: each firm's SAM.gov page lists its points of contact:")
    for i, f in enumerate(firms[:5], 1):
        q = urllib.parse.quote_plus(f"{f['name']} {f.get('city', '')} {f.get('st') or state}")
        print(f"  {i}. https://sam.gov/entity/{f['uei']}/coreData   web: https://www.google.com/search?q={q}")
    os.makedirs(OUT, exist_ok=True)
    for f in firms:
        f["zips"], f["agencies"] = sorted(f["zips"]), sorted(f["agencies"])
    json.dump({"sol": sol, "naics": naics, "state": state, "found": str(dt.date.today()), "firms": firms},
              open(path, "w"), indent=1)
    print(f"\nSaved {os.path.relpath(path, bd.ROOT)}. Add picks to the bid: "
          f"python bid-desk/sub_finder.py {sol} --add 1,2   then draft the ask: python bid-desk/bid_desk.py rfq {sol}")


if __name__ == "__main__":
    main(sys.argv[1:])
