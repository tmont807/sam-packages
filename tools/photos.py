"""Finds and downloads free Unsplash photos for the Projexian website.
search: QUERIES env (| separated) -> out/thumbs + out/photos.json
get:    PICKS env (name=id, comma separated) -> out/full/<name>.jpg + out/credits.json
"""
import json, os, sys, urllib.parse, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Projexian site build)", "Accept": "application/json"}
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60).read()
os.makedirs("out", exist_ok=True)
mode = sys.argv[1]
if mode == "search":
    res = {}
    for q in os.environ["QUERIES"].split("|"):
        q = q.strip()
        try:
            d = json.loads(get("https://unsplash.com/napi/search/photos?" + urllib.parse.urlencode({"query": q, "per_page": 24, "orientation": "landscape"})))
        except Exception as e:
            print("fail", q, e); continue
        keep = []
        for p in d.get("results", []):
            if p.get("premium") or p.get("plus"):
                continue
            keep.append({"id": p["id"], "alt": p.get("alt_description"), "w": p["width"], "h": p["height"],
                         "author": p["user"]["name"], "user": p["user"]["username"], "color": p.get("color")})
            os.makedirs(f"out/thumbs/{q.replace(' ', '_')}", exist_ok=True)
            open(f"out/thumbs/{q.replace(' ', '_')}/{p['id']}.jpg", "wb").write(get(p["urls"]["thumb"]))
            if len(keep) >= 12:
                break
        res[q] = keep
        print(q, len(keep))
    json.dump(res, open("out/photos.json", "w"), indent=1)
else:
    credits = {}
    os.makedirs("out/full", exist_ok=True)
    for pair in os.environ["PICKS"].split(","):
        name, pid = pair.strip().split("=")
        p = json.loads(get(f"https://unsplash.com/napi/photos/{pid}"))
        raw = p["urls"]["raw"] + "&w=2200&q=82&fm=jpg&fit=max"
        open(f"out/full/{name}.jpg", "wb").write(get(raw))
        credits[name] = {"id": pid, "author": p["user"]["name"], "user": p["user"]["username"], "alt": p.get("alt_description")}
        try:
            get(p["links"]["download_location"].replace("https://api.unsplash.com", "https://unsplash.com/napi"))
        except Exception:
            pass
        print("got", name)
    json.dump(credits, open("out/credits.json", "w"), indent=1)
