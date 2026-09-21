"""
fetch_foreign_adversaries.py
Fetches the Foreign Adversaries list under 15 CFR § 791.4 from eCFR.
This is a short list of countries/regimes, not individual companies.
Outputs: output/raw/foreign_adversaries.json
"""

import json
import os
import re
import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")
ECFR_URL = "https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-791/section-791.4"


def fetch():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[ForeignAdversaries] Fetching {ECFR_URL}")

    r = requests.get(ECFR_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    entities = []
    seen = set()

    # eCFR renders regulation text in <div class="section"> or <p> elements
    text_blocks = soup.select(".section-body p, .section p, article p")
    full_text = " ".join(p.get_text(" ", strip=True) for p in text_blocks)

    if not full_text:
        full_text = soup.get_text(" ", strip=True)

    # 15 CFR § 791.4 lists foreign adversaries as a named list of countries/governments
    # Pattern: country names following "means" or listed after a colon
    # Known adversaries as of 2025: China (PRC), Cuba, Iran, DPRK (North Korea), Russia, Venezuela (Maduro)
    known_adversaries = [
        ("China", "People's Republic of China", "CN"),
        ("Cuba", "Republic of Cuba", "CU"),
        ("Iran", "Islamic Republic of Iran", "IR"),
        ("North Korea", "Democratic People's Republic of Korea", "KP"),
        ("Russia", "Russian Federation", "RU"),
        ("Venezuela", "Bolivarian Republic of Venezuela / Maduro Regime", "VE"),
    ]

    # Try to extract from live text; fall back to known list
    extracted = []
    for country, full_name, iso in known_adversaries:
        if country.lower() in full_text.lower() or full_name.lower() in full_text.lower():
            extracted.append((country, full_name, iso))

    # Use extracted if we got hits; otherwise use full known list with a note
    source_note = "Parsed from eCFR live text" if extracted else "Hardcoded from 15 CFR § 791.4 (2025) — verify against current eCFR"
    target_list = extracted if extracted else known_adversaries

    for country, full_name, iso in target_list:
        if country not in seen:
            seen.add(country)
            entities.append({
                "entity_name": full_name,
                "aka": [country],
                "country": iso,
                "source_list": "Foreign Adversaries (15 CFR § 791.4)",
                "list_category": 3,
                "date_added": None,
                "federal_register_cite": "15 CFR § 791.4",
                "notes": source_note,
            })

    out = os.path.join(OUTPUT_DIR, "foreign_adversaries.json")
    with open(out, "w") as f:
        json.dump(entities, f, indent=2)
    print(f"[ForeignAdversaries] {len(entities)} entities → {out}")
    return entities


if __name__ == "__main__":
    fetch()
