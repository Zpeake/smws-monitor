# SMWS Release Monitor

A lightweight Python tool that monitors the [Scotch Malt Whisky Society America](https://smwsa.com) outturn page for new bottle releases and delivers instant personalized notifications via Discord — before the announcement email ever arrives.

Built for SMWS members who are tired of missing limited expressions because they sold out while waiting for the email.

---

## How It Works

1. On startup, loads a local SQLite database of SMWS distillery codes to map cask numbers to distillery names and regions (e.g. `29 → Laphroaig, Islay`)
2. Fetches the SMWS America outturn collection page on a randomized interval (~60 seconds)
3. Extracts product handles using regex and compares against a persisted baseline
4. When new products appear, fetches each product page for details — price, ABV, age, cask type, and flavor profile
5. Assigns a personalized priority tier to each configured user based on their preferences
6. Delivers a color-coded Discord embed to each user's private channel and an optional shared Ntfy push notification

### Priority Tiers

| Priority | Color | Condition |
|----------|-------|-----------|
| 🔴 High Priority | Red | User's priority region, not excluded distillery, under price threshold |
| 🟡 Worth a Look | Yellow | Priority region over threshold, excluded distillery, or peated flavor profile |
| 🟢 FYI | Green | Everything else |

---

## Project Structure

```
smws-monitor/
├── smws_monitor.py       # main monitor script
├── db.py                 # distillery database CLI
├── config.py             # personal config — DO NOT COMMIT (see config.example.py)
├── config.example.py     # template for config.py
├── smws_distilleries.db  # SQLite database (created on first seed, gitignored)
├── known_handles.json    # persists seen products across restarts (gitignored)
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.8+
- A Discord server with webhook URLs configured for each user

### Install dependencies

```bash
pip install requests beautifulsoup4
```

### Configure

Copy the example config and fill in your values:

```bash
cp config.example.py config.py
```

Edit `config.py` with your settings:

```python
OUTTURN_URL    = "https://smwsa.com/collections/whisky"
CHECK_INTERVAL = (45, 75)
NTFY_CHANNEL   = ""         # optional shared push notifications

USERS = [
    {
        "name": "User1",
        "discord_webhook": "",          # Discord channel webhook URL
        "priority_regions": ["Islay"],
        "priority_flavors": ["Bold & Peaty", "Heavily Peated", ...],
        "exclude_distilleries": ["53"], # Caol Ila
        "price_threshold": 175,
    },
]
```

### Set up the distillery database

Seed from the community-maintained SMWS code list:

```bash
python db.py seed
```

Manage entries manually as SMWS adds new distilleries:

```bash
python db.py list
python db.py search "Islay"
python db.py add 168 "New Distillery" "Highland"
python db.py remove 168
```

### Run locally

```bash
python smws_monitor.py
```

---

## Discord Setup

Each user needs a private Discord channel with a webhook:

1. Create a Discord server or use an existing one
2. Create a private channel per user
3. Go to **Channel Settings → Integrations → Webhooks → New Webhook**
4. Copy the webhook URL and add it to that user's `discord_webhook` field in `config.py`

Notifications arrive as color-coded embeds with full bottle details and a direct link to the product page.

---

## GCP Deployment

Deploy to a Google Cloud Platform e2-micro instance for 24/7 monitoring at no cost (free tier).

### Prerequisites

- A GCP account with billing enabled
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated

### Create the VM

```bash
gcloud config set project YOUR_PROJECT_ID

gcloud compute instances create smws-monitor \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud
```

### SSH in and install dependencies

```bash
gcloud compute ssh smws-monitor --zone=us-central1-a
pip3 install requests beautifulsoup4 --break-system-packages
```

### Upload files

From your local repo folder:

```bash
gcloud compute scp smws_monitor.py db.py config.py smws-monitor:~ --zone=us-central1-a
```

### Seed the database and run

```bash
python3 db.py seed
tmux new-session -s smws
python3 smws_monitor.py
```

Detach from tmux with **Ctrl+B then D** — the monitor keeps running after you disconnect.

### Updating config

When preferences change, update `config.py` locally and push to the VM:

```bash
gcloud compute scp config.py smws-monitor:~ --zone=us-central1-a
gcloud compute ssh smws-monitor --zone=us-central1-a
tmux attach -t smws   # Ctrl+C to stop, then restart
python3 smws_monitor.py
```

---

## Optional: Ntfy Push Notifications

In addition to Discord, the monitor supports shared push notifications via [Ntfy](https://ntfy.sh) as a backup channel.

1. Install the Ntfy app on your phone
2. Choose a private channel name and subscribe
3. Add the channel name to `NTFY_CHANNEL` in `config.py`

All subscribers to the channel receive every alert at the highest priority among all configured users.

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| SMWS returns 403 | Alert sent to all channels, monitor pauses |
| SMWS returns 429 | Alert sent, backs off for 5 minutes |
| Zero products detected | Alert sent — possible URL or structure change |
| Product page fetch fails | Logs warning, continues with available details |
| Database not found | Warns to run `db.py seed`, continues without lookup |
| Discord/Ntfy failure | Logs warning, continues without crashing |

---

## Distillery Database

SMWS uses a proprietary numbering system to anonymize distilleries. This project maintains a local SQLite database mapping those codes to distillery names and regions, seeded initially from the community and maintained manually via the `db.py` CLI.

The database supports standard Scottish regions (Islay, Speyside, Highland, Lowland, Campbeltown) as well as international distilleries from Japan, the USA, Australia, Scandinavia, and beyond as SMWS continues to expand its portfolio.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3 |
| HTTP requests | `requests` |
| HTML parsing | `beautifulsoup4` |
| Distillery database | SQLite (stdlib) |
| Notifications | Discord webhooks + Ntfy |
| Hosting | GCP Compute Engine e2-micro (free tier) |
| Session persistence | tmux |

---

## Roadmap

- [ ] Include full tasting notes (nose, palate, finish) in notifications
- [ ] Store detection history in SQLite for a release log
- [ ] Web dashboard showing recent detections and bottle history
- [ ] Expand to monitor all SMWS collections year-round
- [ ] Dockerize for cleaner deployment and portability
