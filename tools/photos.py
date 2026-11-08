"""Finds and downloads freely licensed photos for the Projexian website.
search: QUERIES env (| separated) -> Wikimedia Commons search, public domain / CC0 / CC BY only -> out/thumbs + out/photos.json
get:    PICKS env (name=c:File title  or  name=u:unsplashId), ';' separated -> out/full/<name>.jpg + out/credits.json
"""
import json, os, re, sys, urllib.parse, urllib.request
H = {"User-Agent": "ProjexianSiteBuild/1.0 (https://github.com/tmont807/sam-packages)"}
API = "https://commons.wikimedia.org/w/api.php?"
OK = re.compile(r"public domain|^pd|cc0|cc by(?!-sa)(?!-nc)(?!-nd)", re.I)
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=90).read()
def strip(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()
os.makedirs("out", exist_ok=True)
mode = sys.argv[1]
if mode == "search":
    res = {}
    for q in os.environ["QUERIES"].split("|"):
        q = q.strip(); slug = re.sub(r"\W+", "_", q)
        params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                  "gsrsearch": q + " filetype:bitmap", "gsrlimit": 40, "prop": "imageinfo",
                  "iiprop": "url|size|extmetadata", "iiurlwidth": 360}
        try:
            d = json.loads(get(API + urllib.parse.urlencode(params)))
        except Exception as e:
            print("fail", q, e); continue
        keep = []
        for p in sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 0)):
            ii = (p.get("imageinfo") or [{}])[0]
            md = ii.get("extmetadata") or {}
            lic = strip((md.get("LicenseShortName") or {}).get("value"))
            if not OK.search(lic) or ii.get("width", 0) < 2000 or ii.get("width", 0) < ii.get("height", 1) * 1.2:
                continue
            k = len(keep)
            open_dir = f"out/thumbs/{slug}"; os.makedirs(open_dir, exist_ok=True)
            try:
                open(f"{open_dir}/{k:02d}.jpg", "wb").write(get(ii["thumburl"]))
            except Exception:
                continue
            keep.append({"k": k, "title": p["title"], "w": ii["width"], "h": ii["height"], "license": lic,
                         "artist": strip((md.get("Artist") or {}).get("value"))[:120]})
            if len(keep) >= 12:
                break
        res[q] = keep
        print(q, len(keep))
    json.dump(res, open("out/photos.json", "w"), indent=1)
else:
    credits = {}
    os.makedirs("out/full", exist_ok=True)
    for pair in re.split(r";(?=\s*\w+=[cu]:)", os.environ["PICKS"]):
        if not pair.strip():
            continue
        name, src = pair.strip().split("=", 1)
        try:
            if src.startswith("u:"):
                pid = src[2:]
                data = get(f"https://unsplash.com/photos/{pid}/download?force=true&w=2200")
                credits[name] = {"source": "Unsplash", "id": pid}
            else:
                title = src[2:]
                d = json.loads(get(API + urllib.parse.urlencode({"action": "query", "format": "json", "titles": title,
                    "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 2200})))
                ii = list(d["query"]["pages"].values())[0]["imageinfo"][0]
                md = ii.get("extmetadata") or {}
                data = get(ii["thumburl"])
                credits[name] = {"source": "Wikimedia Commons", "title": title, "page": ii.get("descriptionurl"),
                                 "license": strip((md.get("LicenseShortName") or {}).get("value")),
                                 "artist": strip((md.get("Artist") or {}).get("value"))[:160]}
            open(f"out/full/{name}.jpg", "wb").write(data)
            print("got", name, len(data))
        except Exception as e:
            print("fail", name, e)
    json.dump(credits, open("out/credits.json", "w"), indent=1)
