#!/usr/bin/env python3
"""Match Gmail replies to prospects and update their status. Claude runs this during /brief:

  python leads/replies.py queries [--days 14]   Gmail search queries covering everyone emailed
  python leads/replies.py apply messages.json   update statuses from the messages those queries found

messages.json is a list of {"id", "from", "subject", "snippet", "date"} from Gmail search results.
Each message is handled once (ids kept in leads/replies_seen.txt):
  - "remove", "unsubscribe", "not interested" and similar  -> optout (hashed, never emailed again)
  - a bounce from mailer-daemon naming a prospect's address -> bounced
  - out-of-office auto replies                            -> ignored, prospect stays "sent"
  - anything else from a prospect                          -> replied, with the snippet as a note
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outreach as ob  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN = os.path.join(HERE, "replies_seen.txt")
OPTOUT_RE = re.compile(r"\b(remove|unsubscribe|opt.?out|stop (emailing|sending|contacting)|take (me|us) off|"
                       r"not interested|no thank|do not (contact|email)|don't (contact|email))\b", re.I)
AUTO_RE = re.compile(r"\b(out of (the )?office|automatic reply|auto.?reply|away until|on vacation|"
                     r"limited access to email)\b", re.I)
BOUNCE_FROM = re.compile(r"mailer-daemon|postmaster|mail delivery", re.I)
FREEMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "msn.com",
            "live.com", "comcast.net", "att.net", "sbcglobal.net", "verizon.net", "me.com", "ymail.com"}
ADDR_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")


def addr(s):
    m = ADDR_RE.search(s or "")
    return m.group(0).lower() if m else ""


def emailed(days=None):
    """Every prospect we have emailed: (email, list file, prospect id)."""
    cutoff = str(dt.date.today() - dt.timedelta(days=days)) if days else ""
    out = []
    for f in ob.city_files("all"):
        for p in json.load(open(f)):
            if p.get("email") and p.get("status") != "new" and p.get("sent", "") >= cutoff:
                out.append((p["email"].lower(), f, p["id"]))
    return out


def cmd_queries(a):
    days = int(a[a.index("--days") + 1]) if "--days" in a else 14
    # Search whole company domains: the reply often comes from a coworker, not the address emailed.
    people = sorted({e if e.split("@")[1] in FREEMAIL else e.split("@")[1] for e, _, _ in emailed(days)})
    if not people:
        print("# nobody emailed in that window")
        return
    for i in range(0, len(people), 25):
        chunk = people[i:i + 25]
        print(f"from:({' OR '.join(chunk)}) newer_than:{days}d")
    print(f"from:mailer-daemon newer_than:{days}d")


def cmd_apply(a):
    msgs = json.load(open(a[0]))
    try:
        seen = set(open(SEEN).read().split())
    except OSError:
        seen = set()
    index = {}
    for e, f, pid in emailed():
        index.setdefault(e, (f, pid))
    domains = {e.split("@")[1]: v for e, v in index.items()}
    changes = {"replied": [], "optout": [], "bounced": [], "auto": []}
    for m in msgs:
        if m.get("id") in seen:
            continue
        text = f"{m.get('subject', '')} {m.get('snippet', '')}"
        sender = addr(m.get("from"))
        if BOUNCE_FROM.search(m.get("from", "")):
            hit = next((e for e in ADDR_RE.findall(text) if e.lower() in index), None)
            if hit:
                f, pid = index[hit.lower()]
                set_status(f, pid, "bounced", "")
                changes["bounced"].append(hit)
        else:
            dom = sender.split("@")[-1]
            f_pid = index.get(sender) or (None if dom in FREEMAIL else domains.get(dom))
            if f_pid:
                f, pid = f_pid
                if AUTO_RE.search(text):
                    changes["auto"].append(sender)
                elif OPTOUT_RE.search(text):
                    set_status(f, pid, "optout", "")
                    ob.cmd_optout([sender])
                    changes["optout"].append(sender)
                else:
                    name = set_status(f, pid, "replied", f"{m.get('date', '')[:10]} reply: {m.get('snippet', '')[:160]}")
                    changes["replied"].append(f"{name} <{sender}>: {m.get('snippet', '')[:120]}")
        seen.add(m.get("id"))
    with open(SEEN, "w") as fh:
        fh.write("\n".join(sorted(x for x in seen if x)))
    print(json.dumps(changes, indent=1))


def set_status(f, pid, stage, note):
    rows = json.load(open(f))
    name = ""
    for p in rows:
        if p["id"] == pid:
            name = p["name"]
            # A later stage set by hand (meeting, quoted, won) wins over an automatic "replied".
            if not (stage == "replied" and p.get("status") in ("meeting", "quoted", "won", "lost")):
                p["status"] = stage
            if note:
                p["notes"] = (p.get("notes", "") + " | " + note).strip(" |")
    json.dump(rows, open(f, "w"), indent=0)
    return name


if __name__ == "__main__":
    cmds = {"queries": cmd_queries, "apply": cmd_apply}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])
