"""Download full packages for specific SAM notice IDs (NOTICE_IDS env, comma separated) into packages/."""
import os, sys, json, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_sam_packages as F
for nid in [x.strip() for x in os.environ["NOTICE_IDS"].split(",") if x.strip()]:
    d = F.get_json(f"https://sam.gov/api/prod/opps/v2/opportunities/{nid}")
    att = F.get_json(f"https://sam.gov/api/prod/opps/v3/opportunities/{nid}/resources", {"excludeDeleted": "false", "withScanResult": "false"})
    dd = d.get("data2") or {}
    sol = dd.get("solicitationNumber") or nid; title = dd.get("title") or nid
    due = ((dd.get("solicitation") or {}).get("deadlines") or {}).get("response") or ""
    folder = os.path.join("packages", f"{due[:10]} - {F.clean(sol, 40)} - {F.clean(title)}")
    os.makedirs(folder, exist_ok=True)
    files = [a for a in (((att.get("_embedded") or {}).get("opportunityAttachmentList") or [{}])[0].get("attachments") or []) if a.get("resourceId") and str(a.get("deletedFlag") or "0") != "1"]
    res = []
    for a in files:
        name = F.clean(a.get("name") or a["resourceId"], 150)
        try: res.append((name, F.download(f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{a['resourceId']}/download", os.path.join(folder, name))))
        except Exception as e: res.append((name, f"failed: {e}"))
        time.sleep(0.4)
    desc = re.sub(r"<[^>]+>", " ", ((d.get("description") or [{}])[0] or {}).get("body") or "")
    open(os.path.join(folder, "description.txt"), "w").write(desc)
    json.dump({"noticeId": nid, "solicitationNumber": sol, "title": title, "due": due, "files": res, "setAside": (dd.get("solicitation") or {}).get("setAside")}, open(os.path.join(folder, "notice.json"), "w"), indent=1)
    print(folder, len(res))
