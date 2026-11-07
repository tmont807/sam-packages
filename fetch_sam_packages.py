"""Daily SAM.gov package downloader for Projexian LLC.

Finds new federal solicitations Projexian can bid (small business set-aside or
unrestricted, due 12+ days out, US only) in its service NAICS codes, downloads
every attached file, and saves them under packages/<due> | <solicitation> | <title>/.
Uses the same public data the SAM.gov website loads; no API key needed.
Standard library only.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

NAICS = ["561720", "561730", "561210", "561790", "561710", "562111", "562119",
         "532490", "532120", "484110", "484220", "561990", "238990"]
MIN_DAYS_TO_DUE = 12          # skip anything due sooner than this
RECENT_DAYS = int(os.environ.get("RECENT_DAYS") or 3)  # only notices posted/changed in the last N days
MAX_FILE_MB = 95              # GitHub rejects files over 100 MB
BLOCKED_SET_ASIDES = re.compile(r"SDVOSB|8A|HZ|WOSB|VSA|VSS|IEE|ISBEE", re.I)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages")
HEADERS = {"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0 (Projexian package fetcher)"}


def get_json(url, params=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=180) as r:
        length = int(r.headers.get("Content-Length") or 0)
        if length and length > MAX_FILE_MB * 1024 * 1024:
            return f"skipped (too large: {length // (1024 * 1024)} MB)"
        data = r.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        return "skipped (too large)"
    with open(dest, "wb") as f:
        f.write(data)
    return f"{len(data) // 1024} KB"


def clean(s, n=80):
    s = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", str(s or "")).strip()
    return re.sub(r"\s+", " ", s)[:n]


def already_saved():
    ids = set()
    if os.path.isdir(ROOT):
        for d in os.listdir(ROOT):
            p = os.path.join(ROOT, d, "notice.json")
            if os.path.exists(p):
                try:
                    ids.add(json.load(open(p))["noticeId"])
                except Exception:
                    pass
    return ids


def main():
    now = datetime.now(timezone.utc)
    min_due = now + timedelta(days=MIN_DAYS_TO_DUE)
    recent = now - timedelta(days=RECENT_DAYS)
    saved = already_saved()
    seen, new = set(), []
    skips = {"type": 0, "due_soon": 0, "not_recent": 0, "set_aside": 0, "no_files": 0}

    for naics in NAICS:
        try:
            res = get_json("https://sam.gov/api/prod/sgs/v1/search/", {
                "index": "opp", "page": 0, "mode": "search", "sort": "-modifiedDate",
                "size": 100, "mfe": "true", "is_active": "true", "naics": naics})
        except Exception as e:
            print(f"[{naics}] search failed: {e}")
            continue
        rows = (res.get("_embedded") or {}).get("results") or []
        print(f"[{naics}] {len(rows)} active notices")
        for r in rows:
            nid = r.get("_id")
            if not nid or nid in seen or nid in saved:
                continue
            seen.add(nid)
            ntype = (r.get("type") or {}).get("value", "")
            if not re.search(r"Solicitation|Combined", ntype):
                skips["type"] += 1
                continue
            due = r.get("responseDate")
            changed = r.get("modifiedDate") or r.get("publishDate")
            try:
                if not due or datetime.fromisoformat(due) < min_due:
                    skips["due_soon"] += 1
                    continue
                if changed and datetime.fromisoformat(changed) < recent:
                    skips["not_recent"] += 1
                    continue
            except ValueError:
                continue
            try:
                d = get_json(f"https://sam.gov/api/prod/opps/v2/opportunities/{nid}")
                att = get_json(f"https://sam.gov/api/prod/opps/v3/opportunities/{nid}/resources",
                               {"excludeDeleted": "false", "withScanResult": "false"})
            except Exception as e:
                print(f"  detail failed for {nid}: {e}")
                continue
            dd = d.get("data2") or {}
            set_aside = (dd.get("solicitation") or {}).get("setAside") or ""
            if BLOCKED_SET_ASIDES.search(set_aside):
                skips["set_aside"] += 1
                continue
            pop = dd.get("placeOfPerformance") or {}
            country = (pop.get("country") or {}).get("code")
            if country and country != "USA":
                continue
            lists = ((att.get("_embedded") or {}).get("opportunityAttachmentList") or [{}])
            files = [a for a in (lists[0].get("attachments") or []) if a.get("resourceId") and not a.get("deletedFlag")]
            if not files:
                skips["no_files"] += 1
                continue
            sol = r.get("solicitationNumber") or nid
            folder = os.path.join(ROOT, f"{due[:10]} - {clean(sol, 40)} - {clean(r.get('title'))}")
            os.makedirs(folder, exist_ok=True)
            results = []
            for a in files:
                name = clean(a.get("name") or a["resourceId"], 150)
                url = f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{a['resourceId']}/download"
                try:
                    results.append((name, download(url, os.path.join(folder, name))))
                except Exception as e:
                    results.append((name, f"failed: {e}"))
                time.sleep(0.5)
            notice = {
                "noticeId": nid, "solicitationNumber": sol, "title": r.get("title"), "naics": naics,
                "type": ntype, "setAside": set_aside or "Unrestricted", "due": due,
                "state": (pop.get("state") or {}).get("code", ""), "city": (pop.get("city") or {}).get("name", ""),
                "agency": " > ".join(o.get("name", "") for o in (r.get("organizationHierarchy") or [])),
                "contacts": [{"name": p.get("fullName"), "email": p.get("email"), "phone": p.get("phone")}
                             for p in (dd.get("pointOfContact") or [])],
                "files": [{"name": n, "result": res_} for n, res_ in results],
                "savedAt": now.isoformat(),
            }
            json.dump(notice, open(os.path.join(folder, "notice.json"), "w"), indent=2)
            new.append(notice)
            print(f"  saved {sol}: {len(files)} files -> {folder}")
            time.sleep(0.5)

    os.makedirs(ROOT, exist_ok=True)
    if new:
        with open(os.path.join(ROOT, "INDEX.md"), "a") as f:
            f.write(f"\n## {now.strftime('%Y-%m-%d')}\n\n| Due | Solicitation | Title | Place | Set-aside | Files |\n|---|---|---|---|---|---|\n")
            for n in new:
                place = ", ".join(x for x in (n["city"], n["state"]) if x)
                f.write(f"| {n['due'][:10]} | {n['solicitationNumber']} | {clean(n['title'], 70)} | {place} | {n['setAside']} | {len(n['files'])} |\n")
    print(f"Skipped: {skips}")
    print(f"Done: {len(new)} new packages saved.")


if __name__ == "__main__":
    sys.exit(main())
