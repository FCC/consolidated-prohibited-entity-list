import html
"""
fetch_bis_entity_list.py
Downloads and parses the BIS Entity List (Supp. 4) and Military End-User List (Supp. 7).
Uses the Trade.gov Consolidated Screening List (CSL) bulk JSON download.
Outputs: output/raw/bis_entity_list.json, output/raw/bis_meu_list.json
"""

import json
import os
import re
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")

# data.trade.gov bulk JSON — all CSL sources combined; filter by source field
CSL_JSON_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"
# Cached fallback: downloaded by PowerShell when Python is rate-limited
CSL_LOCAL_CACHE = os.path.join(os.path.dirname(__file__), "..", "output", "csl_raw.json")

EL_SOURCE  = "Entity List (EL) - Bureau of Industry and Security"
MEU_SOURCE = "Military End User (MEU) List - Bureau of Industry and Security"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def sanitize_text(value, max_length=1000):
    """
    Sanitize a string value sourced from untrusted external data (CWE-99).
    - Strips leading/trailing whitespace
    - Removes ASCII control characters (except tab and newline)
    - Truncates to max_length to prevent resource exhaustion
    - Returns empty string for non-string input
    """
    if not isinstance(value, str):
        return ""
    # Strip control characters (keep printable + tab)
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)
    value = html.escape(value, quote=True)
    return value.strip()[:max_length]


def extract_country(addresses_str):
    """Pull the first 2-letter country code found at the end of an address segment."""
    if not addresses_str:
        return ""
    for segment in str(addresses_str).split(";"):
        m = re.search(r",\s*([A-Z]{2})\s*$", segment.strip())
        if m:
            return m.group(1)
    return ""


def parse_record(item, source_list, list_category):
    name = sanitize_text(item.get("name") or "")
    if not name:
        return None
    aka_raw = item.get("alt_names") or ""
    if isinstance(aka_raw, list):
        aka = [sanitize_text(a) for a in aka_raw if sanitize_text(a)]
    else:
        aka = [sanitize_text(a) for a in str(aka_raw).split(";") if sanitize_text(a)]
    addresses = item.get("addresses") or ""
    if isinstance(addresses, list):
        addresses = "; ".join(sanitize_text(str(a)) for a in addresses)
    # Validate date format: accept only ISO-style dates (YYYY-MM-DD or similar)
    raw_date = sanitize_text(item.get("start_date") or "")
    date_added = raw_date if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}$", raw_date) else None
    return {
        "entity_name": name,
        "aka": aka,
        "country": extract_country(addresses),
        "source_list": source_list,
        "list_category": list_category,
        "date_added": date_added,
        "federal_register_cite": sanitize_text(item.get("federal_register_notice") or "") or None,
        "notes": sanitize_text(item.get("license_requirement") or ""),
    }


def load_csl_data():
    """Try Python download first; fall back to local cache."""
    # Try Python
    try:
        print(f"[BIS] Downloading CSL JSON from data.trade.gov")
        r = requests.get(CSL_JSON_URL, headers=HEADERS, timeout=120)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        print(f"[BIS] Downloaded {len(results)} total CSL records")
        return results
    except Exception as e:
        print(f"[BIS] Python download failed ({e}), trying local cache")

    # Fall back to local cache
    if os.path.exists(CSL_LOCAL_CACHE):
        with open(CSL_LOCAL_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        results = data.get("results", data) if isinstance(data, dict) else data
        print(f"[BIS] Loaded {len(results)} records from local cache ({CSL_LOCAL_CACHE})")
        return results

    print("[BIS] ERROR: No CSL data available (download failed and no local cache)")
    return None


def fetch():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    records = load_csl_data()
    if records is None:
        for fname in ("bis_entity_list.json", "bis_meu_list.json"):
            with open(os.path.join(OUTPUT_DIR, fname), "w") as f:
                json.dump([], f)
        return [], []

    entity_entities = [r for r in (parse_record(item, "BIS Entity List", 2)
                                   for item in records if item.get("source") == EL_SOURCE) if r]
    out_el = os.path.join(OUTPUT_DIR, "bis_entity_list.json")
    with open(out_el, "w", encoding="utf-8") as f:
        json.dump(entity_entities, f, indent=2, ensure_ascii=False)
    print(f"[BIS Entity List] {len(entity_entities)} entities -> {out_el}")

    meu_entities = [r for r in (parse_record(item, "BIS Military End-User List", 2)
                                for item in records if item.get("source") == MEU_SOURCE) if r]
    out_meu = os.path.join(OUTPUT_DIR, "bis_meu_list.json")
    with open(out_meu, "w", encoding="utf-8") as f:
        json.dump(meu_entities, f, indent=2, ensure_ascii=False)
    print(f"[BIS MEU List] {len(meu_entities)} entities -> {out_meu}")

    return entity_entities, meu_entities


if __name__ == "__main__":
    fetch()
