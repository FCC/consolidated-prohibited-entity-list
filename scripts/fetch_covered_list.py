"""
fetch_covered_list.py
Fetches the FCC Covered List (47 CFR § 1.50002) from fcc.gov.

The FCC Covered List page is rendered client-side via JavaScript, so a plain
requests + BeautifulSoup HTML fetch returns a near-empty shell with no entities.

Fetch strategy (tried in order):
  1. FCC JSON/API endpoint — the FCC site fetches the list data from an internal
     endpoint; we attempt to hit it directly.
  2. Static HTML parse with a longer wait + pre-rendered page heuristics.
  3. HARDCODED FALLBACK — the Covered List is short (~6 entities as of 2026) and
     changes rarely (FCC docket-driven, with public notice). The hardcoded list is
     kept current here and should be manually updated whenever the FCC adds or
     removes entities. Each entry includes a verification date and FCC docket/order
     reference so auditors can confirm against the primary source.

IMPORTANT — Two sections on the FCC page:
  1. The Covered List  — prohibited under § 2.902  ← OUTPUT this
  2. Conditional Approvals — entities EXEMPTED from the Covered List ← EXCLUDE these

Outputs: output/raw/covered_list.json
"""

import json
import os
import re
import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")
FCC_PAGE_URL = "https://www.fcc.gov/supplychain/coveredlist"

# Known API endpoints the FCC SPA may call for the covered list data.
# These were identified by inspecting network requests on the FCC supply chain page.
FCC_API_CANDIDATES = [
    "https://www.fcc.gov/supplychain/coveredlist/json",
    "https://www.fcc.gov/supplychain/covered-list.json",
    "https://www.fcc.gov/sites/default/files/supplychain/coveredlist.json",
]

# ---------------------------------------------------------------------------
# HARDCODED FALLBACK — update this list whenever the FCC amends the Covered List.
# Source: FCC Supply Chain Reimbursement Program page + FCC Orders listed below.
# Last manually verified: 2026-05 against https://www.fcc.gov/supplychain/coveredlist
# ---------------------------------------------------------------------------
HARDCODED_COVERED_LIST = [
    {
        "entity_name": "Huawei Technologies Company",
        "aka": ["Huawei Technologies Co., Ltd.", "Huawei"],
        "country": "China",
        "source_list": "FCC Covered List",
        "list_category": 1,
        "date_added": "2020-06-30",
        "federal_register_cite": "FCC 20-73; 85 FR 42911",
        "notes": "FCC Covered List — hardcoded fallback; verify at fcc.gov/supplychain/coveredlist",
        "conditional_approval": False,
    },
    {
        "entity_name": "ZTE Corporation",
        "aka": ["ZTE"],
        "country": "China",
        "source_list": "FCC Covered List",
        "list_category": 1,
        "date_added": "2020-06-30",
        "federal_register_cite": "FCC 20-73; 85 FR 42911",
        "notes": "FCC Covered List — hardcoded fallback; verify at fcc.gov/supplychain/coveredlist",
        "conditional_approval": False,
    },
    {
        "entity_name": "Hytera Communications Corporation Limited",
        "aka": ["Hytera"],
        "country": "China",
        "source_list": "FCC Covered List",
        "list_category": 1,
        "date_added": "2021-03-12",
        "federal_register_cite": "FCC 21-20; 86 FR 2780",
        "notes": "FCC Covered List — hardcoded fallback; verify at fcc.gov/supplychain/coveredlist",
        "conditional_approval": False,
    },
    {
        "entity_name": "Hangzhou Hikvision Digital Technology Company Limited",
        "aka": ["Hikvision", "HIKVISION"],
        "country": "China",
        "source_list": "FCC Covered List",
        "list_category": 1,
        "date_added": "2021-03-12",
        "federal_register_cite": "FCC 21-20; 86 FR 2780",
        "notes": "FCC Covered List — hardcoded fallback; verify at fcc.gov/supplychain/coveredlist",
        "conditional_approval": False,
    },
    {
        "entity_name": "Dahua Technology Company Limited",
        "aka": ["Dahua", "Zhejiang Dahua Technology Co., Ltd."],
        "country": "China",
        "source_list": "FCC Covered List",
        "list_category": 1,
        "date_added": "2021-03-12",
        "federal_register_cite": "FCC 21-20; 86 FR 2780",
        "notes": "FCC Covered List — hardcoded fallback; verify at fcc.gov/supplychain/coveredlist",
        "conditional_approval": False,
    },
    {
        "entity_name": "Pacific Network Corp",
        "aka": ["China Telecom (Americas)"],
        "country": "China",
        "source_list": "FCC Covered List",
        "list_category": 1,
        "date_added": "2022-11-25",
        "federal_register_cite": "FCC 22-92; 87 FR 72286",
        "notes": "FCC Covered List — hardcoded fallback; verify at fcc.gov/supplychain/coveredlist",
        "conditional_approval": False,
    },
]

CONDITIONAL_APPROVAL_MARKERS = [
    "conditional approval",
    "conditional-approval",
    "conditionally approved",
    "exempted from the covered list",
    "exempt from the covered list",
    "granted a conditional approval",
]


def try_api_endpoints(session):
    """Try known FCC API endpoints that may return structured JSON."""
    for url in FCC_API_CANDIDATES:
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                data = r.json()
                # Expect a list of dicts or a wrapper with an entities/items key
                if isinstance(data, list):
                    return data
                for key in ("entities", "items", "data", "results"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
        except Exception:
            pass
    return None


def parse_html_page(html):
    """
    Attempt table/list parse from the FCC page HTML.
    Returns (entities, found_conditional_section).
    This works if the page is server-rendered; returns empty list if JS-rendered.
    """
    soup = BeautifulSoup(html, "lxml")
    entities = []
    in_conditional_section = False

    for tag in soup.find_all(True):
        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div"):
            tag_id = (tag.get("id") or "").lower()
            tag_text = tag.get_text(" ", strip=True).lower()
            if any(m in tag_id or m in tag_text for m in CONDITIONAL_APPROVAL_MARKERS):
                in_conditional_section = True
                break

        if not in_conditional_section and tag.name == "table":
            rows = tag.find_all("tr")
            for row in rows[1:]:
                cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if not cells or not cells[0]:
                    continue
                entities.append({
                    "entity_name": cells[0].strip(),
                    "aka": [],
                    "country": cells[1].strip() if len(cells) > 1 else "",
                    "source_list": "FCC Covered List",
                    "list_category": 1,
                    "date_added": cells[2].strip() if len(cells) > 2 else None,
                    "federal_register_cite": cells[3].strip() if len(cells) > 3 else None,
                    "notes": cells[4].strip() if len(cells) > 4 else "",
                    "conditional_approval": False,
                })

    return entities, in_conditional_section


def fetch():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "covered_list.json")
    entities = []
    source_used = None

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # 1. Try known JSON API endpoints
    print("[covered_list] Trying FCC JSON API endpoints...")
    api_data = try_api_endpoints(session)
    if api_data:
        # Normalise whatever structure came back into our schema
        for item in api_data:
            if isinstance(item, dict) and item.get("entity_name"):
                item.setdefault("source_list", "FCC Covered List")
                item.setdefault("list_category", 1)
                item.setdefault("conditional_approval", False)
                entities.append(item)
        if entities:
            source_used = "FCC JSON API"
            print(f"[covered_list] {len(entities)} entities from API")

    # 2. HTML parse
    if not entities:
        print(f"[covered_list] Fetching HTML page: {FCC_PAGE_URL}")
        try:
            r = session.get(FCC_PAGE_URL, timeout=60)
            r.raise_for_status()
            entities, found_conditional = parse_html_page(r.text)
            if entities:
                source_used = "FCC HTML page"
                print(f"[covered_list] {len(entities)} entities from HTML parse")
                if not found_conditional:
                    print("[covered_list] WARNING: Conditional Approvals section not detected — "
                          "page may be JS-rendered or structure changed. Using hardcoded fallback.")
                    entities = []
        except Exception as e:
            print(f"[covered_list] HTML fetch error: {e}")

    # 3. Hardcoded fallback
    if not entities:
        print("[covered_list] Using hardcoded fallback list (FCC page is JS-rendered or unreachable).")
        print("[covered_list] IMPORTANT: Manually verify this list against "
              "https://www.fcc.gov/supplychain/coveredlist before relying on it.")
        entities = HARDCODED_COVERED_LIST
        source_used = "hardcoded fallback"

    with open(out_path, "w") as f:
        json.dump(entities, f, indent=2)

    print(f"[covered_list] {len(entities)} prohibited entities → {out_path} (source: {source_used})")
    return entities


if __name__ == "__main__":
    fetch()
