"""Full SAM.gov sweep: every active solicitation in Projexian's NAICS codes that a new small
business can bid (no 8(a)/SDVOSB/HUBZone/WOSB-only set-asides), due 10+ days out. Downloads each
package to a temp folder, reads the text, and flags size, evaluation method, experience minimums
and whether subcontractor/teaming experience counts. Writes scan/results.json (no documents kept)."""
import json, os, re, sys, time, tempfile, subprocess, urllib.parse, urllib.request, zipfile, io
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from naics_codes import NAICS, NAICS_TITLES
H = {"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0 (Projexian scan)"}
BLOCKED = re.compile(r"8A|8\(a\)|SDVOSB|Service-Disabled|HZ|HUBZone|WOSB|EDWOSB|Women|ISBEE|IEE|VSA|VSS", re.I)
def get(url, params=None, raw=False, timeout=60):
    if params: url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout) as r:
                b = r.read(); return b if raw else json.loads(b.decode("utf-8"))
        except Exception as e:
            if k == 2: raise
            time.sleep(2 + 3 * k)
def text_of(path):
    p = path.lower()
    try:
        if p.endswith(".pdf"):
            return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=90).stdout
        if p.endswith(".docx"):
            z = zipfile.ZipFile(path); x = z.read("word/document.xml").decode("utf8", "ignore")
            return re.sub(r"<[^>]+>", " ", x.replace("</w:p>", "\n"))
        if p.endswith(".xlsx"):
            z = zipfile.ZipFile(path); return " ".join(re.sub(r"<[^>]+>", " ", z.read(n).decode("utf8", "ignore")) for n in z.namelist() if n.startswith("xl/sharedStrings"))
        if p.endswith((".txt", ".htm", ".html")):
            return open(path, errors="ignore").read()
    except Exception:
        pass
    return ""
def snips(T, rx, k=3, w=140):
    return [T[max(0, m.start() - w):m.end() + w].strip() for m in list(re.finditer(rx, T, re.I))[:k]]
MONEY = r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:million|M|K|thousand)?"
def main():
    now = datetime.now(timezone.utc); min_due = now + timedelta(days=10)
    out, seen = [], set()
    for naics in NAICS:
        page = 0
        while page < 6:
            try:
                res = get("https://sam.gov/api/prod/sgs/v1/search/", {"index": "opp", "page": page, "mode": "search", "sort": "-modifiedDate", "size": 100, "mfe": "true", "is_active": "true", "naics": naics})
            except Exception as e:
                print("search fail", naics, e); break
            rows = (res.get("_embedded") or {}).get("results") or []
            for r in rows:
                nid = r.get("_id"); ty = (r.get("type") or {}).get("value", "")
                if not nid or nid in seen or not re.search(r"Solicitation|Combined", ty): continue
                seen.add(nid)
                due = r.get("responseDate")
                try:
                    if not due or datetime.fromisoformat(due) < min_due: continue
                except ValueError: continue
                try:
                    d = get(f"https://sam.gov/api/prod/opps/v2/opportunities/{nid}")
                except Exception: continue
                dd = d.get("data2") or {}
                sa = (dd.get("solicitation") or {}).get("setAside") or ""
                if BLOCKED.search(sa): continue
                pop = dd.get("placeOfPerformance") or {}
                if (pop.get("country") or {}).get("code") not in (None, "", "USA"): continue
                desc = re.sub(r"<[^>]+>", " ", ((d.get("description") or [{}])[0] or {}).get("body") or "")
                T = desc
                try:
                    att = get(f"https://sam.gov/api/prod/opps/v3/opportunities/{nid}/resources", {"excludeDeleted": "false", "withScanResult": "false"})
                    files = [a for a in (((att.get("_embedded") or {}).get("opportunityAttachmentList") or [{}])[0].get("attachments") or []) if a.get("resourceId") and str(a.get("deletedFlag") or "0") != "1"]
                except Exception: files = []
                with tempfile.TemporaryDirectory() as tmp:
                    for a in files[:25]:
                        if (a.get("size") or 0) > 25e6: continue
                        name = re.sub(r"[^\w.\-]+", "_", a.get("name") or a["resourceId"])[:120]
                        try:
                            b = get(f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{a['resourceId']}/download", raw=True, timeout=120)
                            fp = os.path.join(tmp, name); open(fp, "wb").write(b); T += "\n" + text_of(fp)
                        except Exception: pass
                        time.sleep(0.3)
                T = re.sub(r"\s+", " ", T)
                st = (pop.get("state") or {}).get("code", ""); city = (pop.get("city") or {}).get("name", "")
                org = [o.get("name") for o in (r.get("organizationHierarchy") or []) if o.get("name")]
                item = {
                    "id": nid, "sol": r.get("solicitationNumber"), "title": r.get("title"), "naics": naics, "cat": NAICS_TITLES.get(naics, naics),
                    "type": ty, "setAside": sa or "none", "due": due, "state": st, "city": city, "agency": " > ".join(org[-2:]),
                    "files": len(files), "chars": len(T),
                    "lpta": bool(re.search(r"lowest price[d]?,? technically acceptable|\bLPTA\b", T, re.I)),
                    "lowest_price": bool(re.search(r"lowest (evaluated |total )?pric", T, re.I)),
                    "best_value": bool(re.search(r"best value|trade-?off", T, re.I)),
                    "part13": bool(re.search(r"part 13|simplified acquisition", T, re.I)),
                    "neutral_ok": bool(re.search(r"neutral", T, re.I)),
                    "pp_not_evaluated": bool(re.search(r"past performance (will not|is not|shall not) be (evaluated|considered)", T, re.I)),
                    "sub_exp_ok": snips(T, r"(experience|past performance) of (its |their |the offeror'?s )?(proposed |key |major |first[- ]tier )?(subcontractor|teaming partner|team member)s?|(subcontractor|teaming partner|team member)s?'? (experience|past performance) (will|may|shall) be (considered|evaluated|used)", 2),
                    "exp_min": snips(T, r"(minimum of|at least|no (fewer|less) than) (one|two|three|four|five|\(\d\)|\d+) (\(\d\) )?(relevant |similar |recent )?(projects|contracts|references|years of (relevant |similar )?experience)", 3),
                    "exp_dollars": snips(T, r"(each|per) (project|contract|reference)[^.]{0,80}" + MONEY, 2),
                    "no_teaming": bool(re.search(r"teaming arrangements and joint ventures are excluded|subcontractor experience (will not|shall not) be", T, re.I)),
                    "magnitude": snips(T, r"(magnitude|estimated (contract )?(value|amount|cost|price)|price range|ceiling|not[- ]to[- ]exceed|between)[^.]{0,60}" + MONEY, 3),
                    "options": snips(T, r"(four|4|\(4\)|three|3) (\(\d\) )?(option|additional) (years|periods)|base (year|period) (plus|and|with)", 1),
                    "bond": bool(re.search(r"performance bond|payment bond|bid bond|bid guarantee", T, re.I)),
                    "wd": snips(T, r"(janitor|laborer|refuse collector|truckdriver|grounds|maintenance)[^$]{0,40}\$\s?\d\d\.\d\d", 2, 60),
                    "fte": snips(T, r"\b\d{1,3}(\.\d)? (FTEs?|full[- ]time (equivalent|employees|personnel))", 2),
                    "sqft": snips(T, r"\b\d{1,3}(,\d{3})+ ?(square feet|sq\.? ?ft|SF|GSF)\b", 2, 60),
                }
                out.append(item); print(len(out), item["due"][:10], item["setAside"], item["title"][:70], flush=True)
            if len(rows) < 100: break
            page += 1
    os.makedirs("scan", exist_ok=True)
    json.dump({"scanned": now.isoformat(timespec="minutes"), "count": len(out), "items": out}, open("scan/results.json", "w"), indent=1)
    print("done", len(out))
if __name__ == "__main__":
    main()
