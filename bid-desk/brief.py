#!/usr/bin/env python3
"""Data for the /brief summary: new federal bids, deadlines, and the commercial pipeline.

  python bid-desk/brief.py [--days 2]
"""
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bid_desk as bd  # noqa: E402

LEADS = os.path.join(bd.ROOT, "leads", "data")


def federal(days):
    pk, (past, rc), pipe = bd.load_packages(), bd.load_awards(), bd.load_pipe()
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    new = []
    for sol, d in pk.items():
        if d.get("savedAt", "") >= since and pipe.get(sol, {}).get("status", "new") == "new":
            sc, why = bd.score(d, past, rc)
            if sc >= 60:
                new.append((sc, sol, d, why))
    new.sort(key=lambda x: (-x[0], x[2]["_due"] or dt.date.max))
    print(f"## New federal bids worth a look (saved in the last {days} days, score 60+): {len(new)}")
    for sc, sol, d, why in new[:10]:
        where = ", ".join(x for x in (d.get("city"), d.get("state")) if x) or "location in SOW"
        print(f"- {sc} | due {d['_due']} | {sol} | {d.get('title', '')[:70]} | {where} | {'; '.join(why[:3])}")

    print("\n## Active federal bids")
    soon = dt.date.today() + dt.timedelta(days=5)
    active = [(s, r, pk.get(s)) for s, r in pipe.items() if r["status"] in ("pursuing", "subs_asked", "quoted")]
    if not active:
        print("- none in the pipeline yet (bid_desk.py status SOL pursuing)")
    for s, r, d in sorted(active, key=lambda x: (x[2] or {}).get("_due") or dt.date.max):
        due = (d or {}).get("_due")
        flag = "DUE WITHIN 5 DAYS" if due and due <= soon else ""
        quotes = [x for x in r["subs"] if x.get("quote")]
        print(f"- {s} | {r['status']} | due {due} | subs {len(r['subs'])}, quotes {len(quotes)} {flag}")
    sub = sum(1 for r in pipe.values() if r["status"] in ("submitted", "won", "lost"))
    won = sum(1 for r in pipe.values() if r["status"] == "won")
    print(f"- submitted so far: {sub}, won: {won}")


def commercial():
    files = sorted(glob.glob(os.path.join(LEADS, "*.json")))
    files = [f for f in files if not os.path.basename(f).startswith("_")]
    print("\n## Commercial")
    if not files:
        print("- no prospect lists yet: run Actions > Commercial leads")
        return
    tot, ready, replied = {}, 0, []
    for f in files:
        for p in json.load(open(f)):
            st = p.get("status", "new")
            tot[st] = tot.get(st, 0) + 1
            if st == "new" and p.get("email"):
                ready += 1
            if st in ("replied", "meeting"):
                replied.append((p, os.path.basename(f)[:-5]))
    print(f"- {sum(tot.values())} prospects in {len(files)} cities; {ready} with email not yet contacted")
    print("- " + ", ".join(f"{k} {v}" for k, v in sorted(tot.items()) if k != "new"))
    print(f"\n## Replies waiting on you: {len(replied)}")
    for p, city in replied:
        print(f"- {p['name']} ({p['type_label']}, {city}) <{p.get('email')}> [{p['status']}] id {p['id']}: "
              f"{(p.get('notes') or '')[-200:]}")


if __name__ == "__main__":
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 2
    print(f"# Brief data, {dt.date.today()}\n")
    federal(days)
    commercial()
