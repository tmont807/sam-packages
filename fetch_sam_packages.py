"""Daily SAM.gov package downloader for Projexian LLC.

Finds new federal solicitations Projexian can bid (small business set-aside or
unrestricted, due 7+ days out, US only) in its service NAICS codes, downloads
every attached file, and saves them under packages/<due> | <solicitation> | <title>/.
Uses the same public data the SAM.gov website loads; no API key needed.
Standard library only.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from naics_codes import NAICS  # all registered codes

# Product Service Codes searched in addition to NAICS: agencies often file this work under a
# NAICS code Projexian isn't registered for, but the PSC is still right.
PSC = ["S201", "S208", "S205", "S222", "S299", "S216", "W099", "W045", "W054", "V112", "V129"]
# Where documents live when SAM.gov only links out to another system.
DOC_SYSTEMS = {"piee": "PIEE", "dibbs": "DIBBS", "neco.navy": "NECO", "fedconnect": "FedConnect",
               "unison": "Unison", "ebuy": "GSA eBuy"}
MIN_DAYS_TO_DUE = 7           # skip anything due sooner than this
RECENT_DAYS = int(os.environ.get("RECENT_DAYS") or 3)  # only notices posted/changed in the last N days
MAX_FILE_MB = 95              # GitHub rejects files over 100 MB
BLOCKED_SET_ASIDES = re.compile(r"SDVOSB|8A|HZ|WOSB|VSA|VSS|IEE|ISBEE", re.I)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages")
SS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources-sought")
SS_MIN_DAYS = 4             # sources sought / RFIs: skip if response due sooner than this
HEADERS = {"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0 (Projexian package fetcher)"}


def get_json(url, params=None, tries=4):
    """GET with retries: SAM.gov drops or throttles requests now and then."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429 or attempt == tries - 1:
                raise
        except Exception:
            if attempt == tries - 1:
                raise
        time.sleep(5 * 2 ** attempt)


def split_resources(att):
    """SAM.gov 'attachments' mix real files with links out to PIEE, DIBBS etc. Return (files, links)."""
    lists = (att.get("_embedded") or {}).get("opportunityAttachmentList") or [{}]
    items = [a for a in (lists[0].get("attachments") or []) if str(a.get("deletedFlag") or "0") != "1"]
    files = [a for a in items if a.get("type") != "link" and a.get("resourceId")]
    links = [a["uri"] for a in items if a.get("type") == "link" and a.get("uri")]
    return files, links


def doc_status(results, links, description):
    """Tell agents where the documents are: in this repo, in another system, or behind a SAM.gov login."""
    if any(not r.startswith(("failed", "skipped", "restricted")) for _, r in results):
        return "in_repo"
    text = " ".join(links).lower() + " " + (description or "").lower()
    for key, name in DOC_SYSTEMS.items():
        if key in text:
            return f"{name} (not in repo)"
    if any(r.startswith("restricted") for _, r in results):
        return "SAM.gov controlled access (not in repo)"
    if links:
        return "external link (not in repo)"
    return "none posted"


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
    for root in (ROOT, SS_ROOT):
        if not os.path.isdir(root):
            continue
        for d in os.listdir(root):
            p = os.path.join(root, d, "notice.json")
            if os.path.exists(p):
                try:
                    ids.add(json.load(open(p))["noticeId"])
                except Exception:
                    pass
    return ids


def prune(now):
    """Delete package folders whose due date passed more than 3 days ago, to keep the repo small."""
    import shutil
    cutoff = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    n = 0
    for root in (ROOT, SS_ROOT):
        if not os.path.isdir(root):
            continue
        for d in os.listdir(root):
            if re.match(r"\d{4}-\d{2}-\d{2} - ", d) and d[:10] < cutoff:
                shutil.rmtree(os.path.join(root, d), ignore_errors=True); n += 1
    print(f"pruned {n} expired folders")


def main():
    now = datetime.now(timezone.utc)
    prune(now)
    min_due = now + timedelta(days=MIN_DAYS_TO_DUE)
    recent = now - timedelta(days=RECENT_DAYS)
    saved = already_saved()
    seen, new = set(), []
    skips = {"type": 0, "due_soon": 0, "not_recent": 0, "set_aside": 0, "no_files": 0}

    failures = []
    searches = [("naics", n) for n in NAICS] + [("psc", c) for c in PSC]
    for field, code in searches:
        try:
            res = get_json("https://sam.gov/api/prod/sgs/v1/search/", {
                "index": "opp", "page": 0, "mode": "search", "sort": "-modifiedDate",
                "size": 100, "mfe": "true", "is_active": "true", field: code})
        except Exception as e:
            print(f"[{field} {code}] search failed: {e}")
            failures.append(f"search {field} {code}: {e}")
            continue
        rows = (res.get("_embedded") or {}).get("results") or []
        print(f"[{field} {code}] {len(rows)} active notices")
        for r in rows:
            nid = r.get("_id")
            if not nid or nid in seen or nid in saved:
                continue
            seen.add(nid)
            try:
                notice = process(r, nid, field, code, now, min_due, recent, skips)
            except Exception as e:
                print(f"  ERROR on {r.get('solicitationNumber') or nid}: {e}")
                failures.append(f"{r.get('solicitationNumber') or nid}: {e}")
                continue
            if notice:
                new.append(notice)
            time.sleep(0.5)
    return finish(new, now, skips, failures)


def process(r, nid, field, code, now, min_due, recent, skips):
    """Check one notice and save its package. Returns the notice dict, or None if skipped."""
    ntype = (r.get("type") or {}).get("value", "")
    title_txt = r.get("title") or ""
    is_ss = bool(re.search(r"Sources Sought", ntype) or (re.search(r"Special Notice", ntype) and re.search(r"\bRFI\b|Request for Information|Sources Sought|Market Research", title_txt, re.I)))
    if not is_ss and not re.search(r"Solicitation|Combined", ntype):
        skips["type"] += 1
        return None
    due = r.get("responseDate")
    changed = r.get("modifiedDate") or r.get("publishDate")
    try:
        if not due or datetime.fromisoformat(due) < (now + timedelta(days=SS_MIN_DAYS) if is_ss else min_due):
            skips["due_soon"] += 1
            return None
        if changed and datetime.fromisoformat(changed) < recent:
            skips["not_recent"] += 1
            return None
    except ValueError:
        return None
    d = get_json(f"https://sam.gov/api/prod/opps/v2/opportunities/{nid}")
    att = get_json(f"https://sam.gov/api/prod/opps/v3/opportunities/{nid}/resources",
                   {"excludeDeleted": "false", "withScanResult": "false"})
    dd = d.get("data2") or {}
    set_aside = (dd.get("solicitation") or {}).get("setAside") or ""
    if BLOCKED_SET_ASIDES.search(set_aside):
        skips["set_aside"] += 1
        return None
    pop = dd.get("placeOfPerformance") or {}
    country = (pop.get("country") or {}).get("code")
    if country and country != "USA":
        return None
    files, links = split_resources(att)
    description = re.sub(r"<[^>]+>", " ", ((d.get("description") or [{}])[0] or {}).get("body") or "")
    # Keep notices whose documents live in PIEE/DIBBS/etc.: agents still need to know they exist.
    if not files and not links and not is_ss:
        skips["no_files"] += 1
        return None
    naics = ([c for n in (dd.get("naics") or []) for c in (n.get("code") or [])] or [code if field == "naics" else ""])[0]
    sol = r.get("solicitationNumber") or nid
    folder = os.path.join(SS_ROOT if is_ss else ROOT, f"{due[:10]} - {clean(sol, 40)} - {clean(r.get('title'))}")
    os.makedirs(folder, exist_ok=True)
    results = []
    for a in files:
        name = clean(a.get("name") or a["resourceId"], 150)
        if (a.get("accessLevel") or "public") != "public":
            results.append((name, "restricted: request access on SAM.gov"))
            continue
        url = f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{a['resourceId']}/download"
        try:
            results.append((name, download(url, os.path.join(folder, name))))
        except urllib.error.HTTPError as e:
            results.append((name, "restricted: request access on SAM.gov" if e.code in (401, 403) else f"failed: {e}"))
        except Exception as e:
            results.append((name, f"failed: {e}"))
        time.sleep(0.5)
    notice = {
        "noticeId": nid, "solicitationNumber": sol, "title": r.get("title"), "naics": naics,
        "psc": dd.get("classificationCode") or "", "foundBy": f"{field} {code}",
        "type": ntype, "setAside": set_aside or "Unrestricted", "due": due,
        "state": (pop.get("state") or {}).get("code", ""), "city": (pop.get("city") or {}).get("name", ""),
        "agency": " > ".join((o.get("name") or "") for o in (r.get("organizationHierarchy") or [])),
        "contacts": [{"name": p.get("fullName"), "email": p.get("email"), "phone": p.get("phone")}
                     for p in (dd.get("pointOfContact") or [])],
        "files": [{"name": n, "result": res_} for n, res_ in results],
        "links": links,
        "docs": doc_status(results, links, description),
        "kind": "sources_sought" if is_ss else "solicitation",
        "description": description[:6000],
        "savedAt": now.isoformat(),
    }
    json.dump(notice, open(os.path.join(folder, "notice.json"), "w"), indent=2)
    print(f"  saved {sol}: {len(files)} files, {len(links)} links, docs: {notice['docs']} -> {folder}")
    return notice


def finish(new, now, skips, failures):
    for root, kind in ((ROOT, "solicitation"), (SS_ROOT, "sources_sought")):
        batch = [n for n in new if n["kind"] == kind]
        if not batch:
            continue
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "INDEX.md"), "a") as f:
            f.write(f"\n## {now.strftime('%Y-%m-%d')}\n\n| Due | Notice | Title | Place | Set-aside | Files | Docs |\n|---|---|---|---|---|---|---|\n")
            for n in batch:
                place = ", ".join(x for x in (n["city"], n["state"]) if x)
                f.write(f"| {n['due'][:10]} | {n['solicitationNumber']} | {clean(n['title'], 70)} | {place} | "
                        f"{n['setAside']} | {len(n['files'])} | {n['docs']} |\n")
    print(f"Skipped: {skips}")
    print(f"Done: {len(new)} new packages saved, {len(failures)} errors.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### SAM.gov packages {now:%Y-%m-%d}\n\n{len(new)} new packages, {len(failures)} errors.\n\n")
            f.writelines(f"- {x}\n" for x in failures[:50])
    # Fail the run (so the alert fires) only when most searches broke, not for one bad notice.
    search_fail = sum(1 for x in failures if x.startswith("search "))
    if search_fail > (len(NAICS) + len(PSC)) // 2:
        print(f"{search_fail} searches failed: SAM.gov looks down or blocked.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
