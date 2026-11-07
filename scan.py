"""One-off SAM.gov scan: prints open notices matching keywords / NAICS (no downloads)."""
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
H = {"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0 (Projexian scan)"}
def get(url, params=None):
    if params: url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60) as r:
        return json.loads(r.read().decode())
now = datetime.now(timezone.utc)
queries = [q for q in os.environ.get("QUERIES", "").split(";") if q.strip()]
naics = [n for n in os.environ.get("NAICS", "").split(",") if n.strip()]
seen = {}
for spec in [("q", q) for q in queries] + [("naics", n) for n in naics]:
    try:
        res = get("https://sam.gov/api/prod/sgs/v1/search/", {"index": "opp", "page": 0, "mode": "search", "sort": "-modifiedDate", "size": 100, "mfe": "true", "is_active": "true", spec[0]: spec[1]})
    except Exception as e:
        print("search failed", spec, e); continue
    for r in (res.get("_embedded") or {}).get("results") or []:
        due = r.get("responseDate")
        if not due or datetime.fromisoformat(due) < now + timedelta(days=5): continue
        nid = r["_id"]
        if nid in seen: continue
        seen[nid] = r
for nid, r in seen.items():
    try:
        d = get(f"https://sam.gov/api/prod/opps/v2/opportunities/{nid}")
    except Exception:
        d = {}
    dd = d.get("data2") or {}
    pop = dd.get("placeOfPerformance") or {}
    desc = re.sub(r"<[^>]+>", " ", ((d.get("description") or [{}])[0] or {}).get("body") or "")
    print(json.dumps({"id": nid, "sol": r.get("solicitationNumber"), "title": r.get("title"), "type": (r.get("type") or {}).get("value"),
        "due": r.get("responseDate", "")[:10], "naics": dd.get("naics", [{}])[0].get("code") if dd.get("naics") else None,
        "setAside": (dd.get("solicitation") or {}).get("setAside"), "state": (pop.get("state") or {}).get("code"),
        "agency": " > ".join(o.get("name", "") for o in (r.get("organizationHierarchy") or []))[:120],
        "poc": [p.get("email") for p in (dd.get("pointOfContact") or [])][:2], "desc": re.sub(r"\s+", " ", desc)[:3000]}))
print("TOTAL", len(seen))
