"""Download specific SAM.gov notices (by notice ID) into a target folder."""
import json, os, re, sys, urllib.parse, urllib.request
H = {"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0 (Projexian fetch)"}
def get(url, params=None):
    if params: url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60) as r:
        return json.loads(r.read().decode())
def clean(s, n=80):
    return re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", str(s or ""))).strip()[:n]
root = os.environ.get("OUT", "anala")
for nid in [x.strip() for x in os.environ.get("IDS", "").split(",") if x.strip()]:
    d = get(f"https://sam.gov/api/prod/opps/v2/opportunities/{nid}")
    dd = d.get("data2") or {}
    sol = dd.get("solicitationNumber") or nid
    sol = sol.strip()
    due = (dd.get("solicitation") or {}).get("deadlines", {}).get("response") or ""
    folder = os.path.join(root, f"{clean(sol, 60)} - {clean(dd.get('title'))}")
    os.makedirs(folder, exist_ok=True)
    att = get(f"https://sam.gov/api/prod/opps/v3/opportunities/{nid}/resources", {"excludeDeleted": "false", "withScanResult": "false"})
    lists = (att.get("_embedded") or {}).get("opportunityAttachmentList") or [{}]
    files = [a for a in (lists[0].get("attachments") or []) if a.get("resourceId") and str(a.get("deletedFlag") or "0") != "1"]
    for a in files:
        name = clean(a.get("name") or a["resourceId"], 150)
        url = f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{a['resourceId']}/download"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": H["User-Agent"]}), timeout=180) as r:
                open(os.path.join(folder, name), "wb").write(r.read())
        except Exception as e:
            print("file failed", name, e)
    desc = re.sub(r"<[^>]+>", " ", ((d.get("description") or [{}])[0] or {}).get("body") or "")
    open(os.path.join(folder, "notice.txt"), "w").write(f"{dd.get('title')}\n{sol}\nDue: {due}\nContacts: {[p.get('email') for p in dd.get('pointOfContact') or []]}\n\n{desc}")
    print("saved", sol, len(files), "files")
