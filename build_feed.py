"""Builds feed.json for the Projexian website: open federal notices in Projexian's
NAICS codes with a map location, plus a few live counts. No bid numbers or
contacts are published. Standard library only; runs in GitHub Actions.
"""
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

NAICS = ["561720", "561730", "561210", "561790", "561710", "562111", "562119",
         "532490", "532120", "484110", "484220", "561990", "238990"]
HERE = os.path.dirname(os.path.abspath(__file__))
HEADERS = {"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0 (Projexian site feed)"}
GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip"
MAX_ITEMS = 450

STATE_CENTER = {
    "AL": (32.8, -86.8), "AK": (61.4, -150.0), "AZ": (34.2, -111.6), "AR": (34.9, -92.4), "CA": (37.2, -119.5),
    "CO": (39.0, -105.5), "CT": (41.6, -72.7), "DE": (39.0, -75.5), "DC": (38.9, -77.0), "FL": (28.6, -82.4),
    "GA": (32.7, -83.4), "HI": (21.3, -157.8), "ID": (44.4, -114.6), "IL": (40.0, -89.2), "IN": (39.9, -86.3),
    "IA": (42.1, -93.5), "KS": (38.5, -98.4), "KY": (37.5, -85.3), "LA": (31.1, -92.0), "ME": (45.4, -69.2),
    "MD": (39.0, -76.8), "MA": (42.3, -71.8), "MI": (43.8, -84.7), "MN": (46.3, -94.3), "MS": (32.7, -89.7),
    "MO": (38.4, -92.5), "MT": (47.0, -109.6), "NE": (41.5, -99.8), "NV": (39.3, -116.6), "NH": (43.7, -71.6),
    "NJ": (40.2, -74.7), "NM": (34.4, -106.1), "NY": (42.9, -75.5), "NC": (35.6, -79.4), "ND": (47.5, -100.5),
    "OH": (40.3, -82.8), "OK": (35.6, -97.5), "OR": (43.9, -120.6), "PA": (40.9, -77.8), "RI": (41.7, -71.5),
    "SC": (33.9, -80.9), "SD": (44.4, -100.2), "TN": (35.9, -86.4), "TX": (31.5, -99.3), "UT": (39.3, -111.7),
    "VT": (44.1, -72.7), "VA": (37.5, -78.9), "WA": (47.4, -120.5), "WV": (38.6, -80.6), "WI": (44.6, -89.9),
    "WY": (43.0, -107.6), "PR": (18.2, -66.5), "GU": (13.4, 144.8), "VI": (18.3, -64.9), "MP": (15.2, 145.75), "AS": (-14.3, -170.7),
}


def get_json(url, params=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def load_places():
    places = {}
    try:
        req = urllib.request.Request(GAZ, headers={"User-Agent": HEADERS["User-Agent"]})
        data = urllib.request.urlopen(req, timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(data))
        text = z.read(z.namelist()[0]).decode("latin-1")
        lines = text.splitlines()
        head = [h.strip() for h in lines[0].split("\t")]
        iu, inm, ila, ilo = head.index("USPS"), head.index("NAME"), head.index("INTPTLAT"), head.index("INTPTLONG")
        for ln in lines[1:]:
            c = ln.split("\t")
            name = re.sub(r"\s+(city|town|village|CDP|borough|municipality|city and borough|urban county|consolidated government.*|metropolitan government.*|unified government.*)$", "", c[inm].strip(), flags=re.I)
            key = (norm(name), c[iu].strip())
            places.setdefault(key, (float(c[ila]), float(c[ilo].strip())))
    except Exception as e:
        print(f"gazetteer failed: {e}")
    return places


def norm(s):
    s = re.sub(r"[^a-z ]", "", (s or "").lower().replace("saint ", "st ").replace("st. ", "st "))
    return re.sub(r"\s+", " ", s).strip()


def short_title(t):
    t = re.sub(r"^[A-Z0-9]{1,4}--\s*", "", t or "").strip()
    if t.isupper():
        t = t.title()
    return t[:90]


def short_agency(parts):
    names = [p.get("name", "") for p in parts or [] if p.get("name")]
    if not names:
        return ""
    a = names[1] if len(names) > 1 else names[0]
    a = re.sub(r",?\s*DEPARTMENT OF( THE)?$", "", a.strip(), flags=re.I)
    if a.isupper() and len(a) > 6:
        a = a.title().replace("Of", "of").replace("And", "and").replace("The ", "the ")
    return a[:60]


def main():
    now = datetime.now(timezone.utc)
    places = load_places()
    print(f"places loaded: {len(places)}")
    rows, seen = [], set()
    for naics in NAICS:
        try:
            res = get_json("https://sam.gov/api/prod/sgs/v1/search/", {
                "index": "opp", "page": 0, "mode": "search", "sort": "-modifiedDate",
                "size": 100, "mfe": "true", "is_active": "true", "naics": naics})
        except Exception as e:
            print(f"[{naics}] search failed: {e}")
            continue
        for r in (res.get("_embedded") or {}).get("results") or []:
            nid = r.get("_id")
            ntype = (r.get("type") or {}).get("value", "")
            if not nid or nid in seen or not re.search(r"Solicitation|Combined|Sources Sought|Presolicitation", ntype):
                continue
            due = r.get("responseDate")
            try:
                if not due or datetime.fromisoformat(due) < now:
                    continue
            except ValueError:
                continue
            seen.add(nid)
            rows.append((r, naics, ntype, due))
    print(f"open notices: {len(rows)}")
    rows.sort(key=lambda x: x[0].get("publishDate") or "", reverse=True)

    week_ago = (now - timedelta(days=7)).isoformat()
    new_week = sum(1 for r, *_ in rows if (r.get("publishDate") or "") >= week_ago)
    items = []
    for r, naics, ntype, due in rows:
        if len(items) >= MAX_ITEMS:
            break
        try:
            d = get_json(f"https://sam.gov/api/prod/opps/v2/opportunities/{r['_id']}")
        except Exception:
            continue
        dd = d.get("data2") or {}
        pop = dd.get("placeOfPerformance") or {}
        if (pop.get("country") or {}).get("code") not in (None, "", "USA"):
            continue
        st = (pop.get("state") or {}).get("code", "")
        city = (pop.get("city") or {}).get("name", "")
        if not st:
            off = d.get("officeAddress") or dd.get("officeAddress") or {}
            st = off.get("state") or ""
            city = city or (off.get("city") or "")
        st = (st or "").upper()[:2]
        if st not in STATE_CENTER:
            continue
        loc = places.get((norm(city), st))
        precise = bool(loc)
        if not loc:
            loc = STATE_CENTER[st]
        items.append({
            "t": short_title(r.get("title")), "a": short_agency(r.get("organizationHierarchy")),
            "c": city.title() if city.isupper() else city, "s": st,
            "lat": round(loc[0], 3), "lon": round(loc[1], 3), "p": precise,
            "due": due[:10], "n": naics, "k": "ss" if re.search("Sources|Presol", ntype) else "sol",
        })
        time.sleep(0.25)

    def count_dirs(name):
        p = os.path.join(HERE, name)
        return len([x for x in os.listdir(p) if os.path.isdir(os.path.join(p, x))]) if os.path.isdir(p) else 0

    feed = {
        "updated": now.isoformat(timespec="minutes"),
        "stats": {"open": len(rows), "newThisWeek": new_week,
                  "states": len({i["s"] for i in items}),
                  "packages": count_dirs("packages") + count_dirs("sources-sought")},
        "items": items,
    }
    json.dump(feed, open(os.path.join(HERE, "feed.json"), "w"), separators=(",", ":"))
    print(f"feed.json: {len(items)} items, stats {feed['stats']}")


if __name__ == "__main__":
    main()
