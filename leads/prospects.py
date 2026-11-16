#!/usr/bin/env python3
"""Build commercial prospect lists for major cities from OpenStreetMap (public, no key).

  python leads/prospects.py "Kansas City"            one city (name from catalog.CITIES)
  python leads/prospects.py all                      every city in the catalog
  python leads/prospects.py all --types hotel,office --enrich 300
  python leads/prospects.py rotate 6 --enrich 150     the 6 cities refreshed longest ago (weekly job)

--enrich N visits up to N prospect websites per city (homepage and contact page, robots.txt
respected, one request per second) to find a business email when OpenStreetMap has none.

Output per city: leads/data/<city>.json (merged with earlier runs, so status and notes survive)
and leads/data/<city>.csv, best prospects first. Runs in GitHub Actions (leads.yml).
"""
import csv
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import BUYERS, CITIES, SERVICES, slug  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OVERPASS = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
UA = "ProjexianLeads/1.0 (+https://projexian.com)"
PER_TYPE_CAP = 1500

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
BAD_EMAIL = re.compile(r"(\.(png|jpe?g|gif|svg|webp|css|js)$|example\.|sentry|wixpress|domain\.com|"
                       r"yourname|email\.com$|@2x|godaddy|squarespace|schema\.org|cloudflare)", re.I)
GOOD_BOX = ("facilities", "facility", "operations", "ops", "manager", "office", "admin", "info", "contact", "hello")
CONTACT_PATHS = ("", "/contact", "/contact-us", "/about")


def overpass(query):
    body = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=200) as r:
                return json.loads(r.read())["elements"]
        except Exception as e:
            wait = 20 * (attempt + 1)
            print(f"    overpass error ({e}); retry in {wait}s", flush=True)
            time.sleep(wait)
    return []


def fetch_type(city, key):
    _, lat, lon, km = city[0], city[2], city[3], city[4]
    parts = "".join(f"nwr(around:{km * 1000},{lat},{lon}){f};" for f in BUYERS[key][1])
    return overpass(f"[out:json][timeout:180];({parts});out tags center {PER_TYPE_CAP};")


def first(t, *keys):
    for k in keys:
        if t.get(k):
            return t[k].split(";")[0].strip()
    return ""


def normalize(el, key, city):
    t = el.get("tags", {})
    addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
    p = {
        "id": f"{el['type'][0]}{el['id']}", "name": t.get("name", "").strip(), "type": key,
        "type_label": BUYERS[key][0], "brand": t.get("brand") or t.get("operator") or "",
        "address": addr, "city": t.get("addr:city") or city[0], "state": t.get("addr:state") or city[1],
        "zip": t.get("addr:postcode", ""),
        "website": first(t, "website", "contact:website", "url"),
        "email": first(t, "email", "contact:email"),
        "phone": first(t, "phone", "contact:phone"),
        "size_hint": first(t, "building:levels", "rooms", "beds", "capacity"),
        "lat": el.get("lat") or el.get("center", {}).get("lat"),
        "lon": el.get("lon") or el.get("center", {}).get("lon"),
    }
    if p["website"] and not p["website"].startswith("http"):
        p["website"] = "https://" + p["website"]
    return p


def score(p):
    w = BUYERS[p["type"]][2]
    s = w * 10
    s += 25 if p["email"] else 0
    s += 10 if p["website"] else 0
    s += 5 if p["phone"] else 0
    s += 5 if p["address"] else 0
    try:
        s += min(int(re.sub(r"\D", "", p["size_hint"]) or 0), 20) // 2
    except ValueError:
        pass
    # National chains buy facility services through corporate contracts; local is the easier sell.
    s -= 15 if p["brand"] and p["brand"] != p["name"] else 0
    return s


def pick_email(found, website):
    host = urllib.parse.urlparse(website).hostname or ""
    host = host[4:] if host.startswith("www.") else host
    cands = [e.lower().rstrip(".") for e in found if not BAD_EMAIL.search(e)]
    if not cands:
        return ""
    same = [e for e in cands if host and e.endswith("@" + host)]
    pool = same or cands
    pool.sort(key=lambda e: next((i for i, b in enumerate(GOOD_BOX) if e.startswith(b)), len(GOOD_BOX)))
    return pool[0]


def emails_in(page):
    page = html.unescape(page).replace("[at]", "@").replace("(at)", "@")
    mailto = re.findall(r"mailto:([^\"'?>\s]+)", page, re.I)
    return mailto + EMAIL_RE.findall(page)


_robots = {}


def allowed(url):
    parts = urllib.parse.urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return rp is None or rp.can_fetch(UA, url)


def enrich(p):
    found = []
    base = p["website"].rstrip("/")
    for path in CONTACT_PATHS:
        url = base + path
        if not allowed(url):
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                if "html" not in (r.headers.get("Content-Type") or ""):
                    continue
                found += emails_in(r.read(600_000).decode("utf-8", "ignore"))
        except Exception:
            pass
        time.sleep(1)
        if pick_email(found, p["website"]):
            break
    return pick_email(found, p["website"])


def run_city(city, types, enrich_n):
    path = os.path.join(DATA, slug(city[0], city[1]))
    old = {}
    if os.path.exists(path + ".json"):
        old = {p["id"]: p for p in json.load(open(path + ".json"))}
    found = {}
    for key in types:
        els = fetch_type(city, key)
        n = 0
        for el in els:
            p = normalize(el, key, city)
            if not p["name"] or p["id"] in found:
                continue
            found[p["id"]] = p
            n += 1
        print(f"  {BUYERS[key][0]:<24} {n}", flush=True)
        time.sleep(3)
    # Keep everything from earlier runs; refresh facts, preserve outreach state and found emails.
    for pid, p in found.items():
        prev = old.get(pid, {})
        p["status"] = prev.get("status", "new")
        p["notes"] = prev.get("notes", "")
        p["email"] = p["email"] or prev.get("email", "")
        p["email_source"] = prev.get("email_source") or ("osm" if p["email"] else "")
        p["checked_site"] = prev.get("checked_site", False)
    merged = {**old, **found}
    todo = sorted((p for p in merged.values() if p["website"] and not p["email"] and not p.get("checked_site")),
                  key=lambda p: -BUYERS[p["type"]][2])[:enrich_n]
    for i, p in enumerate(todo, 1):
        e = enrich(p)
        p["checked_site"] = True
        if e:
            p["email"], p["email_source"] = e, "website"
        if i % 25 == 0:
            print(f"  checked {i}/{len(todo)} websites", flush=True)
    rows = sorted(merged.values(), key=lambda p: -score(p))
    for p in rows:
        p["score"] = score(p)
        p["services"] = ", ".join(SERVICES[s] for s in BUYERS[p["type"]][3][:5])
    os.makedirs(DATA, exist_ok=True)
    json.dump(rows, open(path + ".json", "w"), indent=0)
    cols = ["score", "name", "type_label", "address", "city", "state", "zip", "email", "phone", "website",
            "services", "status", "notes", "id"]
    with open(path + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    emails = sum(1 for p in rows if p["email"])
    print(f"  {city[0]}: {len(rows)} prospects, {emails} with email -> {os.path.relpath(path, HERE)}.csv")
    return len(rows), emails


def main(a):
    if not a:
        sys.exit(__doc__)
    opt = lambda k, v: a[a.index(k) + 1] if k in a else v  # noqa: E731
    types = opt("--types", ",".join(BUYERS)).split(",")
    bad = [t for t in types if t not in BUYERS]
    if bad:
        sys.exit(f"unknown types {bad}; choose from {list(BUYERS)}")
    want = a[0].lower()
    stamp_path = os.path.join(DATA, "_refreshed.json")
    try:
        stamps = json.load(open(stamp_path))
    except (OSError, ValueError):
        stamps = {}
    if want == "rotate":
        n = int(a[1]) if len(a) > 1 and a[1].isdigit() else 6
        cities = sorted(CITIES, key=lambda c: stamps.get(slug(c[0], c[1]), ""))[:n]
    else:
        cities = CITIES if want == "all" else [c for c in CITIES if want in (c[0].lower(), slug(c[0], c[1]))]
    if not cities:
        sys.exit(f"unknown city {a[0]!r}; choose from: " + ", ".join(c[0] for c in CITIES))
    total = [0, 0]
    for c in cities:
        print(f"{c[0]}, {c[1]}", flush=True)
        n, e = run_city(c, types, int(opt("--enrich", 0)))
        total[0] += n
        total[1] += e
        stamps[slug(c[0], c[1])] = time.strftime("%Y-%m-%d %H:%M")
        json.dump(stamps, open(stamp_path, "w"), indent=0, sort_keys=True)
    print(f"\nDone: {total[0]} prospects, {total[1]} with email, {len(cities)} cities.")


if __name__ == "__main__":
    main(sys.argv[1:])
