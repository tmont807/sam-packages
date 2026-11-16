# Commercial leads

Prospect lists of private commercial buyers in 50 major metros, matched to the services each
type of buyer pays for, plus cold-email batches and reply tracking. All work is subbed to local
crews, the same as the federal side.

## 1. Build the lists (GitHub Actions)

**Actions → Commercial leads → Run workflow.** Inputs:
- **cities**: `rotate` (the 6 lists updated longest ago), one city like `Kansas City`, or `all`
- **types**: blank for all buyer types, or e.g. `hotel,medical,property_mgr`
- **enrich**: how many prospect websites per city to check for an email (default 150)

It also runs every Monday on `rotate`, so all 50 cities refresh about every two months, and each
run checks more websites for emails. Results land in `leads/data/<city>.csv` (open in Excel or
Google Sheets) and `.json`. Reruns keep each prospect's status and notes.

The source is OpenStreetMap: buildings and businesses with names, addresses, websites, phones,
and sometimes emails. Coverage is best for hotels, restaurants, medical, schools, churches and
dealerships, and thinner for office tenants. Where OpenStreetMap has a website but no email, the
enrich step reads the homepage and contact page (respecting robots.txt, one request a second)
and keeps the best business address (facilities@, operations@, office@, info@ first).

## 2. Who buys what

17 buyer types, 24 services. Each email leads with the three services that buyer type buys most
(see `catalog.py`):

| Buyer | Leads with |
|---|---|
| Property manager | janitorial, landscaping, snow |
| Hotel | hood cleaning, grease traps, pest control |
| Restaurant | grease traps, hood cleaning, pest control |
| Medical / senior living | janitorial, medical waste, shredding / hood, grease |
| Warehouse | janitorial, hauling, pest control |
| Shopping center | lot sweeping and striping, pressure washing, snow |
| Builder | post-construction cleanup, portable restrooms, junk removal |

Prospect score: bigger and recurring buyer types first, then those with an email, website, phone
and address. National chains rank lower, because they buy through corporate contracts.

## 3. Send

```
cp leads/config.example.json leads/config.json      # fill in your name, phone and real postal address
python leads/outreach.py preview kansas-city-mo      # read the first 3 emails
python leads/outreach.py batch kansas-city-mo --size 50
python leads/outreach.py batch all --size 200 --types hotel,restaurant
```

`batch` writes `leads/batches/<date>-<list>.csv` (email, company, subject, body) for a mail-merge
or cold-email tool, and marks those prospects `sent` so the next batch picks up new ones.

Sending advice:
- Send from a separate domain, such as `getprojexian.com`, with its own inboxes. Cold email from
  projexian.com risks its reputation, and then your bids and invoices land in spam.
- Warm up new inboxes, then stay around 30 to 50 emails a day per inbox.
- The law (CAN-SPAM) requires your real postal address, an honest From line and subject, and
  that you honor opt-outs within 10 business days. The template includes the address and opt-out
  line, and `batch` refuses to run until `config.json` has the address.

## 4. Track

Replies are handled by `/brief` in Claude: it searches Gmail for mail from every company you
emailed (by domain, so a coworker's reply counts), then runs `leads/replies.py`, which marks
replies, honors opt-outs ("remove", "unsubscribe", "not interested"), marks bounces, and ignores
out-of-office auto replies. Replies must reach the connected Gmail, so either send from it or
forward the sending inbox to it.

By hand:

```
python leads/outreach.py mark kansas-city-mo n123456 replied "wants janitorial quote, 3 buildings"
python leads/outreach.py optout someone@business.com     # every list, forever
python leads/outreach.py stats                           # per city: sent, replied, meeting, won, reply rate
```

Stages: new, sent, replied, meeting, quoted, won, lost, optout, bounced. When a prospect wants a
quote, find the sub the same way as federal work (local crews for that service), and price with
the bid desk's markup math.
