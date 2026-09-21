import html
"""
fetch_treasury_ns_cmic.py
Fetches the Treasury NS-CMIC (Non-SDN Chinese Military-Industrial Complex Companies) list.
Primary: XML download. Fallback: HTML page scrape.
Outputs: output/raw/treasury_ns_cmic.json
"""

import json
import os
import re
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup


def sanitize_text(value, max_length=1000):
    """
    Sanitize a string sourced from untrusted external data (CWE-80, CWE-99).
    - Strips HTML tags (defense-in-depth beyond BeautifulSoup's get_text)
    - Removes ASCII control characters
    - Truncates to max_length
    - Returns empty string for non-string input
    """
    if not isinstance(value, str):
        return ""
    # Strip any residual HTML tags
    value = re.sub(r"<[^>]*>", "", value)
    # Remove control characters (keep printable + tab)
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)
    value = html.escape(value, quote=True)
    return value.strip()[:max_length]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")

XML_URL = "https://www.treasury.gov/ofac/downloads/nscmic.xml"
PAGE_URL = "https://home.treasury.gov/policy-issues/financial-sanctions/consolidated-sanctions-list/non-sdn-chinese-military-industrial-complex-companies-list-ns-cmic-list"


def parse_xml(xml_bytes):
    entities = []
    try:
        root = ET.fromstring(xml_bytes)
        ns = {"ofac": "https://sanctionslistservice.ofac.treas.gov/api/PublicationsService/v2"}

        # Try namespaced parse first
        entries = root.findall(".//ofac:sdnEntry", ns) or root.findall(".//sdnEntry")

        for entry in entries:
            # Entity name
            last = sanitize_text(entry.findtext(".//lastName") or entry.findtext(".//ofac:lastName", namespaces=ns) or "")
            first = sanitize_text(entry.findtext(".//firstName") or entry.findtext(".//ofac:firstName", namespaces=ns) or "")
            name = f"{last} {first}".strip() if first else last.strip()

            if not name:
                continue

            # AKAs
            akas = []
            for aka in entry.findall(".//aka") or entry.findall(".//ofac:aka", ns):
                aka_last = sanitize_text(aka.findtext("lastName") or aka.findtext("ofac:lastName", namespaces=ns) or "")
                aka_first = sanitize_text(aka.findtext("firstName") or aka.findtext("ofac:firstName", namespaces=ns) or "")
                aka_name = f"{aka_last} {aka_first}".strip() if aka_first else aka_last.strip()
                if aka_name:
                    akas.append(aka_name)

            # Country
            address = entry.find(".//address") or entry.find(".//ofac:address", ns)
            country = ""
            if address is not None:
                country = sanitize_text(address.findtext("country") or address.findtext("ofac:country", namespaces=ns) or "")

            entities.append({
                "entity_name": name,
                "aka": akas,
                "country": country or "China",  # NS-CMIC is inherently China-focused
                "source_list": "Treasury NS-CMIC List",
                "list_category": 2,
                "date_added": None,
                "federal_register_cite": "31 CFR Part 586; E.O. 13959",
                "notes": "Non-SDN Chinese Military-Industrial Complex Companies List",
            })
    except ET.ParseError as e:
        print(f"[CMIC] XML parse error: {e}")

    return entities


def scrape_page_fallback():
    """Fallback: scrape the Treasury webpage for NS-CMIC company names."""
    print("[CMIC] Attempting HTML page scrape fallback")
    r = requests.get(PAGE_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    entities = []

    # Company name signals -- must contain at least one of these to be accepted
    COMPANY_SIGNALS = (
        " Co.", " Corp.", " Corporation", " Inc.", " Ltd.", " LLC", " L.L.C.",
        " Group", " Holdings", " Technology", " Technologies", " Systems",
        " Microelectronics", " Semiconductor", " Aviation", " Aerospace",
        " Defense", " Defence", " Industries", " International", " Investments",
        " Enterprises", " Solutions", " Networks", " Communications",
        " Electronics", " Manufacturing", " Energy", " Capital", " Partners",
    )
    # Navigation/boilerplate patterns to reject
    NAV_PATTERNS = (
        "OFAC", "Sanctions", "SDN", "Contact", "Search", "Submit",
        "About", "Recent", "List Service", "Programs", "Country Information",
        "Cuba", "Iran", "Russia", "Korea", "Venezuela", "Narcotics", "Cyber",
    )

    for li in soup.select("ul li, ol li"):
        text = sanitize_text(li.get_text(strip=True))
        if not text or len(text) < 5 or len(text) > 300:
            continue
        # Reject navigation boilerplate
        if any(nav in text for nav in NAV_PATTERNS):
            continue
        # Must contain at least one company name signal
        if not any(sig in text for sig in COMPANY_SIGNALS):
            continue
        entities.append({
                "entity_name": text,
                "aka": [],
                "country": "China",
                "source_list": "Treasury NS-CMIC List",
                "list_category": 2,
                "date_added": None,
                "federal_register_cite": "31 CFR Part 586",
                "notes": "Parsed from Treasury HTML page",
            })
    return entities


def fetch():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    entities = []

    # Try XML first
    try:
        print(f"[CMIC] Fetching XML from {XML_URL}")
        r = requests.get(XML_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        entities = parse_xml(r.content)
        print(f"[CMIC] Parsed {len(entities)} entities from XML")
    except Exception as e:
        print(f"[CMIC] XML fetch failed: {e}")

    # Fallback to HTML scrape
    if not entities:
        try:
            entities = scrape_page_fallback()
            print(f"[CMIC] Scraped {len(entities)} entities from HTML")
        except Exception as e:
            print(f"[CMIC] HTML scrape also failed: {e}")

    out = os.path.join(OUTPUT_DIR, "treasury_ns_cmic.json")
    with open(out, "w") as f:
        json.dump(entities, f, indent=2)
    print(f"[CMIC] {len(entities)} entities → {out}")
    return entities


if __name__ == "__main__":
    fetch()
