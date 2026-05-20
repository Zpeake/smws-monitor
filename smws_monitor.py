#!/usr/bin/env python3
"""
SMWS Release Monitor
Watches the SMWS America outturn page and sends personalized Discord
DMs + shared Ntfy push notification + Mac notification when new
products appear, with distillery/region info from a local SQLite DB.
"""

import re
import json
import time
import sqlite3
import subprocess
import random
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

from config import NTFY_CHANNEL, USERS, OUTTURN_URL, CHECK_INTERVAL

KNOWN_FILE     = Path(__file__).parent / "known_handles.json"
DB_FILE        = Path(__file__).parent / "smws_distilleries.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────

def notify_mac(title: str, message: str, sound: str = "Glass"):
    """Send a native macOS notification with sound (local only)."""
    script = (
        f'display notification "{message}" '
        f'with title "{title}" '
        f'sound name "{sound}"'
    )
    subprocess.run(["osascript", "-e", script], check=False)


def notify_ntfy(title: str, message: str, ntfy_priority: str = "default"):
    """Send a shared push notification via Ntfy."""
    if not NTFY_CHANNEL:
        print("  📱 Ntfy skipped (channel not configured)")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_CHANNEL}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": ntfy_priority,
                "Tags": "whisky",
            },
            timeout=10
        )
        print("  📱 Ntfy notification sent")
    except Exception as e:
        print(f"  ⚠️  Ntfy failed: {e}")


def notify_discord(webhook_url: str, title: str, message: str, color: int):
    """Send a personalized Discord embed message via webhook."""
    if not webhook_url:
        return
    try:
        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,     # hex color as int: red=15158332, yellow=16776960, green=5763719
            }]
        }
        requests.post(webhook_url, json=payload, timeout=10)
        print(f"  💬 Discord notification sent")
    except Exception as e:
        print(f"  ⚠️  Discord failed: {e}")


def send_system_alert(title: str, message: str, ntfy_priority: str = "high"):
    """Send a system-level alert (errors, blocks) via all channels."""
    notify_mac(title, message, sound="Basso")
    notify_ntfy(title, message, ntfy_priority=ntfy_priority)
    for user in USERS:
        notify_discord(user["discord_webhook"], title, message, 15158332)


# ─────────────────────────────────────────────
# DISTILLERY LOOKUP
# ─────────────────────────────────────────────

def build_distillery_map() -> dict:
    """Load distillery codes from local SQLite database."""
    if not DB_FILE.exists():
        print("  ⚠️  Database not found. Run: python db.py seed")
        return {}

    print("Loading distillery map from local database...")
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT code, name, region FROM distilleries").fetchall()
    conn.close()

    distillery_map = {row[0]: {"name": row[1], "region": row[2]} for row in rows}
    print(f"  ✅ Loaded {len(distillery_map)} distillery codes.")
    return distillery_map


# ─────────────────────────────────────────────
# PRODUCT PAGE DETAIL FETCH
# ─────────────────────────────────────────────

def fetch_product_details(handle: str) -> dict:
    """Fetch individual product page and extract details."""
    url = f"https://smwsa.com/products/{handle}"
    details = {"url": url, "price": None, "abv": None,
               "age": None, "cask_type": None, "flavor": None, "title": None}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        h1 = soup.find("h1")
        if h1:
            details["title"] = h1.get_text(strip=True)

        price_el = soup.find(string=re.compile(r"\$\d+"))
        if price_el:
            match = re.search(r"\$(\d+)", price_el)
            if match:
                details["price"] = int(match.group(1))

        text = soup.get_text(" ", strip=True)

        abv_match = re.search(r"(\d+\.?\d*)\s*%", text)
        if abv_match:
            details["abv"] = abv_match.group(1)

        age_match = re.search(r"(\d+)\s*year", text, re.IGNORECASE)
        if age_match:
            details["age"] = age_match.group(1)

        flavor_tags = [
            "Bold & Peaty", "Coastal & Maritime", "Heavily Peated",
            "Oily & Coastal", "Lightly Peated", "Peated",
            "Dried Fruits & Spices", "Deep Rich & Dried Fruits",
            "Juicy Oak & Vanilla", "Light & Delicate",
            "Ripe Fruits & Honey", "Sweet Fruity & Mellow",
            "Spicy & Dry", "Spicy & Sweet", "Sweet & Zesty",
            "Old & Dignified", "Young & Spritely", "Fragrant & Floral",
            "Smoky & Fruity",
        ]
        for tag in flavor_tags:
            if tag.lower() in text.lower():
                details["flavor"] = tag
                break

        cask_match = re.search(
            r"(first.fill|refill|second.fill)[^,\n<]{0,60}(hogshead|butt|barrel|puncheon)",
            text, re.IGNORECASE
        )
        if cask_match:
            details["cask_type"] = cask_match.group(0).strip()

        time.sleep(random.uniform(1, 3))    # polite delay between product fetches

    except requests.RequestException as e:
        print(f"  ⚠️  Could not fetch product page for {handle}: {e}")

    return details


# ─────────────────────────────────────────────
# PRIORITY LOGIC
# ─────────────────────────────────────────────

PRIORITY_LEVELS = {
    "🔴 HIGH PRIORITY":  {"ntfy": "urgent", "sound": "Glass",  "color": 15158332},
    "🟡 WORTH A LOOK":   {"ntfy": "high",    "sound": "Ping",   "color": 16776960},
    "🟢 FYI":            {"ntfy": "default", "sound": "Tink",   "color": 5763719},
}


def determine_priority_for_user(user: dict, distillery_code: str,
                                distillery_info: dict, details: dict) -> str:
    """Returns priority label for a specific user."""
    region   = distillery_info.get("region", "").lower()
    price    = details.get("price")
    flavor   = details.get("flavor", "") or ""

    in_priority_region = any(r.lower() in region for r in user["priority_regions"])
    in_priority_flavor = flavor in user["priority_flavors"]
    is_excluded        = distillery_code in user["exclude_distilleries"]
    under_threshold    = price is None or price <= user["price_threshold"]

    if in_priority_region and not is_excluded and under_threshold:
        return "🔴 HIGH PRIORITY"

    if (in_priority_region or in_priority_flavor) and not is_excluded:
        return "🟡 WORTH A LOOK"

    if in_priority_flavor:
        return "🟡 WORTH A LOOK"

    return "🟢 FYI"


# ─────────────────────────────────────────────
# HANDLE PARSING
# ─────────────────────────────────────────────

def parse_handle(handle: str) -> tuple:
    """
    Extract distillery code and cask number from a product handle.
    'cask-no-29-288' → ('29', '288')
    'batch-39'       → (None, None)
    """
    match = re.match(r"cask-no-(\d+)-(\d+)", handle)
    if match:
        return match.group(1), match.group(2)
    return None, None


# ─────────────────────────────────────────────
# PAGE SCRAPING
# ─────────────────────────────────────────────

def get_current_handles(known_handles: set) -> set:
    """
    Fetch the outturn page and return a set of product handles.
    Includes error handling for blocks, rate limits, and empty results.
    """
    resp = requests.get(OUTTURN_URL, headers=HEADERS, timeout=15)

    if resp.status_code == 403:
        send_system_alert("⚠️ SMWS Monitor", "Blocked by SMWS (403) — check the script!")
        raise requests.RequestException("403 Forbidden")

    if resp.status_code == 429:
        send_system_alert("⚠️ SMWS Monitor", "Rate limited (429) — backing off 5 minutes")
        time.sleep(300)
        raise requests.RequestException("429 Rate Limited")

    resp.raise_for_status()

    handles = set(re.findall(r'href="/products/([a-z0-9-]+)"', resp.text))
    excluded = {"gift-card"}
    handles = handles - excluded

    if len(handles) == 0 and len(known_handles) > 0:
        send_system_alert(
            "⚠️ SMWS Monitor",
            "Zero products found — URL or page structure may have changed!"
        )
        raise requests.RequestException("Zero handles — possible structure change")

    return handles


# ─────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────

def load_known_handles() -> set:
    if KNOWN_FILE.exists():
        return set(json.loads(KNOWN_FILE.read_text()))
    return set()


def save_known_handles(handles: set):
    KNOWN_FILE.write_text(json.dumps(list(handles)))


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  SMWS Release Monitor")
    print("=" * 50)

    distillery_map = build_distillery_map()

    print("\nFetching current product list (baseline)...")
    saved = load_known_handles()

    try:
        known_handles = get_current_handles(saved)
        print(f"  ✅ {len(known_handles)} products currently known. Watching for new ones...\n")
    except requests.RequestException as e:
        print(f"  ❌ Could not reach SMWS site: {e}")
        print("  Check your internet connection and try again.")
        return

    known_handles = known_handles | saved
    save_known_handles(known_handles)

    while True:
        try:
            current_handles = get_current_handles(known_handles)
            new_handles = current_handles - known_handles

            if not new_handles:
                interval = random.randint(*CHECK_INTERVAL)
                print(f"  No change — {len(current_handles)} products. "
                      f"Checking again in {interval}s...")
                time.sleep(interval)
                continue

            print(f"\n🚨 {len(new_handles)} new product(s) detected!")

            for handle in new_handles:
                dist_code, cask_num = parse_handle(handle)

                if dist_code and dist_code in distillery_map:
                    dist_info = distillery_map[dist_code]
                elif dist_code:
                    dist_info = {"name": f"Distillery #{dist_code}", "region": "Unknown"}
                else:
                    dist_info = {"name": "Special Release", "region": "Unknown"}

                print(f"  Fetching details for {handle}...")
                details = fetch_product_details(handle)

                cask_label = (f"Cask {dist_code}.{cask_num}"
                              if dist_code else handle.replace("-", " ").title())
                dist_name  = dist_info["name"]
                region     = dist_info["region"]
                price_str  = f"${details['price']}" if details["price"] else "Price N/A"
                abv_str    = f"{details['abv']}%" if details["abv"] else ""
                age_str    = f"{details['age']}yo" if details["age"] else ""
                flavor_str = details["flavor"] or ""
                title_str  = details["title"] or ""

                print(f"\n  {dist_name} ({region}) — {cask_label}")
                if title_str:
                    print(f"  '{title_str}'")
                print(f"  {' | '.join(filter(None, [age_str, abv_str, flavor_str]))}")
                print(f"  {price_str}")
                print(f"  {details['url']}")

                notif_body = "\n".join(filter(None, [
                    f"{dist_name} ({region}) | {cask_label}",
                    f"'{title_str}'" if title_str else None,
                    " | ".join(filter(None, [age_str, abv_str, flavor_str])),
                    price_str,
                    details["url"],
                ]))

                # Send personalized Discord DM to each user
                top_ntfy_priority = "default"
                top_sound = "Tink"
                priority_order = ["🔴 HIGH PRIORITY", "🟡 WORTH A LOOK", "🟢 FYI"]

                for user in USERS:
                    priority = determine_priority_for_user(
                        user, dist_code or "", dist_info, details
                    )
                    p = PRIORITY_LEVELS[priority]
                    print(f"  → {user['name']}: {priority}")

                    notify_discord(
                        user["discord_webhook"],
                        f"{priority} — New SMWS Drop",
                        notif_body,
                        p["color"]
                    )

                    # Track highest priority for shared notifications
                    if priority_order.index(priority) < priority_order.index(
                        "🟢 FYI" if top_ntfy_priority == "default"
                        else "🟡 WORTH A LOOK" if top_ntfy_priority == "high"
                        else "🔴 HIGH PRIORITY"
                    ):
                        top_ntfy_priority = p["ntfy"]
                        top_sound = p["sound"]

                # Shared notifications at highest priority
                notify_mac(f"🥃 New SMWS Drop", notif_body, sound=top_sound)
                notify_ntfy(f"🥃 New SMWS Drop", notif_body, ntfy_priority=top_ntfy_priority)
                print()

            known_handles = known_handles | new_handles
            save_known_handles(known_handles)

        except requests.RequestException as e:
            interval = random.randint(*CHECK_INTERVAL)
            print(f"  ⚠️  Fetch error: {e} — retrying in {interval}s")
            time.sleep(interval)


if __name__ == "__main__":
    main()
