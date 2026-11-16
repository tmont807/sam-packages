"""One-time backfill: add "links", "docs" and "psc" to notice.json files saved before the
downloader recorded them, and relabel link-type "files" that could never download.

  python tools/backfill_docs.py
"""
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import fetch_sam_packages as F  # noqa: E402


def result_of(f):
    return (f.get("result") if isinstance(f, dict) else f[1]) or ""


def name_of(f):
    return (f.get("name") if isinstance(f, dict) else f[0]) or ""


def main():
    paths = sorted(glob.glob(os.path.join(ROOT, "packages", "*", "notice.json")) +
                   glob.glob(os.path.join(ROOT, "sources-sought", "*", "notice.json")))
    done = errors = 0
    for p in paths:
        n = json.load(open(p))
        if "docs" in n:
            continue
        try:
            att = F.get_json(f"https://sam.gov/api/prod/opps/v3/opportunities/{n['noticeId']}/resources",
                             {"excludeDeleted": "false", "withScanResult": "false"})
            d = F.get_json(f"https://sam.gov/api/prod/opps/v2/opportunities/{n['noticeId']}")
        except Exception as e:
            print(f"skip {n.get('solicitationNumber')}: {e}")
            errors += 1
            continue
        files, links = F.split_resources(att)
        link_ids = {a.get("resourceId") for a in
                    (((att.get("_embedded") or {}).get("opportunityAttachmentList") or [{}])[0].get("attachments") or [])
                    if a.get("type") == "link"}
        kept = []
        for f in n.get("files", []):
            # Link entries were saved under their resourceId as the name and always failed with HTTP 400.
            if name_of(f) in link_ids:
                continue
            r = result_of(f)
            if "401" in r or "403" in r:
                r = "restricted: request access on SAM.gov"
            kept.append({"name": name_of(f), "result": r})
        n["files"] = kept
        n["links"] = links
        n["psc"] = (d.get("data2") or {}).get("classificationCode") or ""
        n["docs"] = F.doc_status([(x["name"], x["result"]) for x in kept], links, n.get("description", ""))
        json.dump(n, open(p, "w"), indent=2)
        done += 1
        if done % 50 == 0:
            print(f"{done} updated", flush=True)
        time.sleep(0.3)
    print(f"Backfilled {done} notices, {errors} errors.")


if __name__ == "__main__":
    main()
