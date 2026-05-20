#!/usr/bin/env python3
"""
SMWS Distillery Database CLI
Manages a local SQLite database of SMWS distillery codes.
Seeded once from WhiskySaga, maintained manually from there.

Usage:
  python db.py list                        # show all entries
  python db.py search <query>              # search by name or region
  python db.py add <code> <name> <region>  # add or update an entry
  python db.py remove <code>               # remove an entry
  python db.py seed                        # re-seed from WhiskySaga
"""

import sys
import sqlite3
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DB_FILE        = Path(__file__).parent / "smws_distilleries.db"
WHISKYSAGA_URL = "https://www.whiskysaga.com/smws-codes"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS distilleries (
            code       TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            region     TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────

def cmd_list():
    """List all distilleries sorted by code."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT code, name, region FROM distilleries ORDER BY CAST(code AS INTEGER)"
    ).fetchall()
    conn.close()

    if not rows:
        print("Database is empty. Run: python db.py seed")
        return

    print(f"\n{'CODE':<8} {'DISTILLERY':<35} {'REGION'}")
    print("─" * 65)
    for code, name, region in rows:
        print(f"{code:<8} {name:<35} {region}")
    print(f"\n{len(rows)} entries total.")


def cmd_search(query: str):
    """Search by name or region (case-insensitive)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT code, name, region FROM distilleries
           WHERE LOWER(name) LIKE ? OR LOWER(region) LIKE ?
           ORDER BY CAST(code AS INTEGER)""",
        (f"%{query.lower()}%", f"%{query.lower()}%")
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No results for '{query}'.")
        return

    print(f"\n{'CODE':<8} {'DISTILLERY':<35} {'REGION'}")
    print("─" * 65)
    for code, name, region in rows:
        print(f"{code:<8} {name:<35} {region}")
    print(f"\n{len(rows)} result(s).")


def cmd_add(code: str, name: str, region: str):
    """Add a new entry or update an existing one."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO distilleries (code, name, region, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(code) DO UPDATE SET
               name=excluded.name,
               region=excluded.region,
               updated_at=datetime('now')""",
        (code, name, region)
    )
    conn.commit()
    conn.close()
    print(f"  ✅ Saved: {code} → {name} ({region})")


def cmd_remove(code: str):
    """Remove an entry by code."""
    conn = get_conn()
    cursor = conn.execute("DELETE FROM distilleries WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    if cursor.rowcount:
        print(f"  ✅ Removed code {code}.")
    else:
        print(f"  ⚠️  Code {code} not found.")


def cmd_seed():
    """Seed the database from WhiskySaga. Skips existing entries by default."""
    print("Seeding from WhiskySaga...")
    try:
        resp = requests.get(WHISKYSAGA_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ❌ Could not reach WhiskySaga: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    conn = get_conn()
    added = updated = skipped = 0

    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) >= 3:
            code   = cells[0].get_text(strip=True)
            name   = cells[1].get_text(strip=True)
            region = cells[2].get_text(strip=True)
            if not code.isdigit():
                continue

            existing = conn.execute(
                "SELECT name, region FROM distilleries WHERE code = ?", (code,)
            ).fetchone()

            if existing is None:
                conn.execute(
                    "INSERT INTO distilleries (code, name, region) VALUES (?, ?, ?)",
                    (code, name, region)
                )
                added += 1
            elif existing != (name, region):
                print(f"  ⚠️  Conflict on code {code}: "
                      f"DB has '{existing[0]} / {existing[1]}', "
                      f"WhiskySaga has '{name} / {region}'. Keeping DB version.")
                skipped += 1
            else:
                skipped += 1

    conn.commit()
    conn.close()
    print(f"  ✅ Seed complete — {added} added, {updated} updated, {skipped} unchanged.")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

USAGE = """
Usage:
  python db.py list
  python db.py search <query>
  python db.py add <code> <name> <region>
  python db.py remove <code>
  python db.py seed
"""

def main():
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        return

    cmd = args[0].lower()

    if cmd == "list":
        cmd_list()

    elif cmd == "search" and len(args) == 2:
        cmd_search(args[1])

    elif cmd == "add" and len(args) == 4:
        cmd_add(args[1], args[2], args[3])

    elif cmd == "remove" and len(args) == 2:
        cmd_remove(args[1])

    elif cmd == "seed":
        cmd_seed()

    else:
        print(USAGE)


if __name__ == "__main__":
    main()
