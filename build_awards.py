"""Builds awards.json for the Projexian website from USAspending.gov (public, no key):
- past: recent federal contract awards per state + NAICS for every open opportunity in feed.json
- recompetes: awards in Projexian's NAICS codes whose period of performance ends in the next 12 months
Standard library only; runs in GitHub Actions.
"""
import json, os, re, time, urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
FIELDS = ["Award ID", "Recipient Name", "Award Amount", "Start Date", "End Date", "Awarding Agency", "Awarding Sub Agency", "Description", "Place of Performance State Code", "NAICS"]
NAICS = ["561720", "561730", "561210", "561790", "561710", "562111", "562119", "532490", "532120", "484110", "484220", "561990", "238990"]


def post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "ProjexianSiteBuild/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(6 * (attempt + 1))


def clean(row):
    def num(v):
        try:
            return round(float(v or 0))
        except Exception:
            return 0
    naics = row.get("NAICS")
    if isinstance(naics, dict):
        naics = naics.get("code")
    return {"id": row.get("Award ID"), "r": (row.get("Recipient Name") or "").title()[:80], "amt": num(row.get("Award Amount")),
            "start": (row.get("Start Date") or "")[:10], "end": (row.get("End Date") or "")[:10],
            "ag": (row.get("Awarding Sub Agency") or row.get("Awarding Agency") or "")[:70],
            "desc": re.sub(r"^IGF::\w+::IGF\s*", "", row.get("Description") or "")[:140], "st": row.get("Place of Performance State Code") or "", "n": naics or "",
            "gid": row.get("generated_internal_id") or ""}


def search(naics, state=None, start=None, limit=6, page=1):
    today = date.today()
    f = {"award_type_codes": ["A", "B", "C", "D"], "naics_codes": {"require": naics},
         "time_period": [{"start_date": (start or today - timedelta(days=3 * 365)).isoformat(), "end_date": today.isoformat()}]}
    if state:
        f["place_of_performance_locations"] = [{"country": "USA", "state": state}]
    body = {"filters": f, "fields": FIELDS, "sort": "Award Amount", "order": "desc", "limit": limit, "page": page, "subawards": False}
    return [clean(x) for x in post(body).get("results", [])]


def main():
    feed = json.load(open(os.path.join(HERE, "feed.json")))
    combos = sorted({(i["s"], i["n"]) for i in feed["items"]})
    past = {}
    for st, n in combos:
        try:
            past[f"{st}|{n}"] = search([n], st)
        except Exception as e:
            print("past fail", st, n, e)
        time.sleep(0.3)
    today = date.today()
    horizon = (today + timedelta(days=365)).isoformat()
    rec = []
    for n in NAICS:
        for page in (1, 2):
            try:
                rows = search([n], None, today - timedelta(days=6 * 365), 100, page)
            except Exception as e:
                print("recompete fail", n, e)
                break
            rec += [r for r in rows if r["end"] and today.isoformat() <= r["end"] <= horizon and r["amt"] >= 25000]
            if len(rows) < 100:
                break
            time.sleep(0.3)
    seen, uniq = set(), []
    for r in sorted(rec, key=lambda x: x["end"]):
        if r["id"] in seen:
            continue
        seen.add(r["id"]); uniq.append(r)
    out = {"updated": today.isoformat(), "past": past, "recompetes": uniq[:300]}
    json.dump(out, open(os.path.join(HERE, "awards.json"), "w"), separators=(",", ":"))
    print(f"awards.json: {len(past)} combos, {sum(len(v) for v in past.values())} past awards, {len(uniq)} recompetes")


if __name__ == "__main__":
    main()
