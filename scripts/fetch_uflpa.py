"""
fetch_uflpa.py
Fetches the DHS UFLPA Entity List published by the Forced Labor Enforcement Task Force.
Parses the HTML tables from the DHS entity list page.
Outputs: output/raw/uflpa.json
"""

import json
import os
import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")

DHS_PAGE = "https://www.dhs.gov/uflpa-entity-list"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Column header variants used on the DHS page
NAME_HEADERS = {"name of entity", "entity name", "name"}
DATE_HEADERS = {"effective date", "date added", "date"}


def parse_uflpa_tables(soup):
    """Extract entity names from all tables on the DHS UFLPA entity list page."""
    entities = []
    seen = set()
    tables = soup.find_all("table")
    print(f"[UFLPA] Found {len(tables)} table(s) on the page")

    for table_idx, table in enumerate(tables):
        rows = table.find_all("tr")
        if not rows:
            continue

        # Detect header row
        header_cells = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        name_col = next((i for i, h in enumerate(header_cells) if h in NAME_HEADERS), None)
        date_col = next((i for i, h in enumerate(header_cells) if h in DATE_HEADERS), None)

        if name_col is None:
            # No recognised header — try first column as name
            name_col = 0

        count_added = 0
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) <= name_col:
                continue
            name = cells[name_col].strip()
            if not name or len(name) < 3:
                continue
            if name.lower() in NAME_HEADERS:
                continue  # skip repeated header rows
            if name in seen:
                continue
            seen.add(name)
            date_added = cells[date_col].strip() if date_col is not None and len(cells) > date_col else None
            entities.append({
                "entity_name": name,
                "aka": [],
                "country": "CN",  # UFLPA targets Xinjiang/China supply chains
                "source_list": "DHS UFLPA Entity List",
                "list_category": 2,
                "date_added": date_added,
                "federal_register_cite": None,
                "notes": "Uyghur Forced Labor Prevention Act — 19 U.S.C. § 4681",
            })
            count_added += 1

        print(f"[UFLPA] Table {table_idx}: {count_added} entities (headers: {header_cells[:3]})")

    return entities


def fetch():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, "uflpa.json")
    print(f"[UFLPA] Fetching {DHS_PAGE}")

    try:
        r = requests.get(DHS_PAGE, headers=HEADERS, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"[UFLPA] ERROR: Could not fetch DHS UFLPA page: {e}")
        with open(out, "w") as f:
            json.dump([], f)
        return []

    soup = BeautifulSoup(r.text, "lxml")
    entities = parse_uflpa_tables(soup)

    if not entities:
        print("[UFLPA] WARNING: No entities extracted — page structure may have changed")

    with open(out, "w", encoding="utf-8") as f:
        json.dump(entities, f, indent=2, ensure_ascii=False)
    print(f"[UFLPA] {len(entities)} entities -> {out}")
    return entities


if __name__ == "__main__":
    fetch()
