#!/usr/bin/env python3
"""Find local subcontractors for a package: companies already paid by the federal government for
the same kind of work (same NAICS) in the same state, from USAspending.gov (public, no key).

A company that already did this work for an agency nearby knows the paperwork, pays wage-determination
rates and is registered in SAM.gov, which makes it the fastest sub to get a usable quote from.

  python bid-desk/sub_finder.py SOL                  ranked list, saved to bid-desk/subs/SOL.json
  python bid-desk/sub_finder.py SOL --state MO       when the notice has no place of performance
  python bid-desk/sub_finder.py SOL --years 5 --top 15
  python bid-desk/sub_finder.py SOL --add 1,3        add picks to the bid's pipeline record

Commercial jobs (no solicitation): companies based in a city that do a given service.
  python bid-desk/sub_finder.py --service janitorial --city "Kansas City" --state MO
  python bid-desk/sub_finder.py --naics 561730 --city Denver --state CO
Services: see SERVICE_NAICS below (same keys as leads/catalog.py).

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

# Commercial service -> the NAICS code federal buyers file that work under.
SERVICE_NAICS = {
    "janitorial": "561720", "windows": "561720", "floors": "561740", "pressure": "561790",
    "grounds": "561730", "snow": "561790", "pest": "561710", "waste": "562111", "grease": "562998",
    "hood": "561790", "restrooms": "562991", "hvac": "238220", "plumbing": "238220",
    "electrical": "238210", "painting": "238320", "parking": "561790", "security": "561612",
    "junk": "562119", "moving": "484210", "fire": "561990", "construction_clean": "561720",
    "medwaste": "562112", "rental": "532490", "shred": "561990",
}


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


def awards(naics, state, years, pages=3, city=None):
    """Federal awards for this NAICS: performed in the state, or (city given) won by firms based in that city."""
    today = dt.date.today()
    where = ({"recipient_locations": [{"country": "USA", "state": state, "city": city.upper()}]} if city
             else {"place_of_performance_locations": [{"country": "USA", "state": state}]})
    body = {"filters": {"award_type_codes": ["A", "B", "C", "D"], "naics_codes": {"require": [naics]}, **where,
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
    f["nonprofit"] = bool(t & {"nonprofit", "nonprofit_organization", "community_development_corporations"}) \
        or "SHELTERED WORKSHOP" in f["name"].upper() or "GOODWILL" in f["name"].upper()
    f["certs"] = [lbl for key, lbl in (("service_disabled_veteran_owned_business", "SDVOSB"),
                                       ("women_owned_small_business", "WOSB"), ("historically_underutilized_business_zone", "HUBZone"),
                                       ("8a_program_participant", "8(a)"), ("veteran_owned_business", "VOSB"))
                  if key in t]


def rank(f, place_city, state):
    s = min(f["awards"], 6) * 5                                     # repeat federal work
    s += 15 if f["last"] >= (dt.date.today() - dt.timedelta(days=540)).isoformat() else 0  # active lately
    s += 20 if f.get("small") else (-25 if "small" in f else 0)     # set-aside compliance
    s -= 30 if f["total"] > TOO_BIG else 0
    s -= 40 if f.get("nonprofit") else 0                            # AbilityOne workshops don't take subwork
    if f.get("st"):
        s += 10 if f["st"] == state else -15                        # based in-state, not just worked there
    if place_city and f.get("city", "").upper() == place_city.upper():
        s += 15
    return s


def main(a):
    if not a:
        sys.exit(__doc__)
    opt = lambda k, v: a[a.index(k) + 1] if k in a else v  # noqa: E731
    if a[0] in ("--service", "--naics"):
        return commercial(a, opt)
    if a[0].startswith("-"):
        sys.exit(__doc__)
    sol, d = bd.find(a[0])
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

    firms = search(naics, state, years, top, d.get("city"), None,
                   f"{sol}: {d.get('title')}\nSearching federal awards for NAICS {naics} "
                   f"({bd.NAICS_TITLES.get(naics, '?')}) in {state}, last {years} years...")
    save(path, {"sol": sol, "naics": naics, "state": state}, firms)
    print(f"Add picks to the bid: python bid-desk/sub_finder.py {sol} --add 1,2   "
          f"then draft the ask: python bid-desk/bid_desk.py rfq {sol}")


def commercial(a, opt):
    svc = opt("--service", "")
    naics = opt("--naics", "") or SERVICE_NAICS.get(svc, "")
    city, state = opt("--city", ""), opt("--state", "").upper()
    if not naics or not city or len(state) != 2:
        sys.exit("Need --service (one of " + ", ".join(SERVICE_NAICS) + ") or --naics, plus --city and --state.")
    years, top = int(opt("--years", 5)), int(opt("--top", 12))
    firms = search(naics, state, years, top, city, city,
                   f"{svc or naics} crews based in {city}, {state}: firms with federal awards under NAICS {naics} "
                   f"({bd.NAICS_TITLES.get(naics, '?')}), last {years} years...")
    name = f"{city.lower().replace(' ', '-').replace('.', '')}-{state.lower()}-{svc or naics}"
    save(os.path.join(OUT, "commercial", name + ".json"), {"service": svc, "naics": naics, "city": city, "state": state}, firms)


def search(naics, state, years, top, place_city, base_city, banner):
    print(banner)
    firms = group(awards(naics, state, years, city=base_city))
    if len(firms) < 5 and base_city:
        print(f"Only {len(firms)} based in {base_city}; widening to all of {state}.")
        firms = group(awards(naics, state, years))
    if len(firms) < 5 and len(naics or "") == 6:
        print(f"Only {len(firms)} found; widening to NAICS {naics[:4]}xx.")
        firms = group(awards(naics[:4], state, years, city=base_city)) or group(awards(naics[:4], state, years))
    firms.sort(key=lambda f: (-min(f["awards"], 6), -int(f["last"] >= "2025"), f["total"]))
    for f in firms[: top * 2]:
        profile(f)
    for f in firms:
        f["score"] = rank(f, place_city, state)
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
        if f.get("nonprofit"):
            flags.append("nonprofit")
        print(f"{i:>2}  {f['name'][:36]:<36} {f.get('city', '')[:16]:<16} {f['awards']:>6} "
              f"${f['total']:>11,.0f}  {f['last'][:7]}  {' '.join(flags)}")
    print("\nContact: each firm's SAM.gov page lists its points of contact:")
    for i, f in enumerate(firms[:5], 1):
        q = urllib.parse.quote_plus(f"{f['name']} {f.get('city', '')} {f.get('st') or state}")
        print(f"  {i}. https://sam.gov/entity/{f['uei']}/coreData   web: https://www.google.com/search?q={q}")
    return firms


def save(path, meta, firms):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for f in firms:
        f["zips"], f["agencies"] = sorted(f["zips"]), sorted(f["agencies"])
    json.dump({**meta, "found": str(dt.date.today()), "firms": firms}, open(path, "w"), indent=1)
    print(f"\nSaved {os.path.relpath(path, bd.ROOT)}.")


if __name__ == "__main__":
    main(sys.argv[1:])
