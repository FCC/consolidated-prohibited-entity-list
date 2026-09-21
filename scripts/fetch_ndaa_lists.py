"""
fetch_ndaa_lists.py
Loads named company lists for NDAA FY2023 § 5949 (Pub. L. 117-263) and
NDAA FY2021 § 1260H (Pub. L. 116-283) from the curated fallback file.

Neither section contains an inline list of companies in the statutory PDF:
  - § 5949 names exactly three semiconductor companies (SMIC, CXMT, YMTC) in
    the body of the statute, plus affiliates to be designated by Commerce/DoD.
  - § 1260H defines "Chinese military companies" by reference to the DoD annual
    list (published separately at media.defense.gov), not inline in the PDF.

PDF parsing of these sections is therefore unreliable and produces false positives
(statutory headings, boilerplate text). The authoritative source is
references/ndaa_fallback.json, which is manually maintained.

To update the lists: edit references/ndaa_fallback.json directly.

Outputs: output/raw/ndaa_5949.json, output/raw/ndaa_1260h.json
"""

import json
import os
import re
import requests
import pdfplumber
from io import BytesIO

SCRIPT_DIR = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output", "raw")
FALLBACK_PATH = os.path.join(SCRIPT_DIR, "..", "references", "ndaa_fallback.json")

NDAA_SOURCES = {
    "5949": {
        "label": "NDAA FY2023 § 5949",
        "pub_law": "Pub. L. 117-263",
        "list_category": 2,
        # Match exactly "SEC. 5949" or "SECTION 5949"
        "section_start_pattern": re.compile(r"SEC(?:TION)?\.?\s+5949\b", re.IGNORECASE),
        # Stop when we hit the NEXT section at the same level: SEC. 5950
        "section_stop_pattern": re.compile(r"^\s*SEC(?:TION)?\.?\s+5950\b", re.IGNORECASE),
        "urls": [
            "https://www.govinfo.gov/content/pkg/PLAW-117publ263/pdf/PLAW-117publ263.pdf",
            "https://www.congress.gov/117/plaws/publ263/PLAW-117publ263.pdf",
        ],
        "output_file": "ndaa_5949.json",
    },
    "1260h": {
        "label": "NDAA FY2021 § 1260H",
        "pub_law": "Pub. L. 116-283",
        "list_category": 2,
        # Match "SEC. 1260H" or "SEC. 1260H." etc.
        "section_start_pattern": re.compile(r"SEC(?:TION)?\.?\s+1260H\b", re.IGNORECASE),
        # Stop at SEC. 1260I (next lettered section) or SEC. 1261
        "section_stop_pattern": re.compile(r"^\s*SEC(?:TION)?\.?\s+1260I\b|^\s*SEC(?:TION)?\.?\s+1261\b", re.IGNORECASE),
        "urls": [
            "https://www.govinfo.gov/content/pkg/PLAW-116publ283/pdf/PLAW-116publ283.pdf",
            "https://www.congress.gov/116/plaws/publ283/PLAW-116publ283.pdf",
        ],
        "output_file": "ndaa_1260h.json",
    },
}


def download_pdf(urls):
    for url in urls:
        try:
            print(f"  Trying {url}")
            r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"  Failed: {e}")
    return None


def extract_section_text(pdf_bytes, start_pattern, stop_pattern):
    """
    Scan the PDF page-by-page for the section header matching start_pattern.
    Once found, collect lines until stop_pattern matches a line — meaning we've
    reached the NEXT section at the same level. This avoids the premature-stop
    bug caused by matching any "SEC. NNN" line inside the section body.

    Returns the captured section text as a single string, or "" if not found.
    """
    capturing = False
    section_lines = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            for line in text.split("\n"):
                if not capturing:
                    if start_pattern.search(line):
                        capturing = True
                        section_lines.append(line)
                else:
                    # Check for the section-end boundary
                    if stop_pattern.search(line):
                        print(f"  Section boundary found on page {page_num}: '{line.strip()[:80]}'")
                        return "\n".join(section_lines)
                    section_lines.append(line)

    if section_lines:
        return "\n".join(section_lines)
    return ""


def parse_companies_from_section(section_text, source_label, pub_law, list_category):
    """
    Parse company names from an NDAA section.

    NDAA company lists appear in several formats depending on the section:
      - Numbered list:  "(1) Huawei Technologies."   or  "(1) HUAWEI TECHNOLOGIES."
      - Lettered list:  "(A) ZTE Corporation."
      - Plain list:     "Hikvision" on its own line (less common)

    We try patterns in priority order and stop at the first that yields results.
    We explicitly exclude lines that are clearly structural / statutory boilerplate
    rather than company names.
    """
    BOILERPLATE = re.compile(
        r"^(the\s+|a\s+|an\s+|in\s+|of\s+|and\s+|or\s+|to\s+|for\s+|"
        r"section\b|subsection\b|paragraph\b|subparagraph\b|"
        r"sec\.\s*\d|pub\.\s*l\.|title\s+\w|chapter\s+\w|"
        r"amendment|revision|repeal|effective|requirement|authorization|"
        r"acquisition|activities|community|construction|developers|"
        r"disability|monitoring|oversight|processes|promotion|reporting|"
        r"countering|financing|terrorism|intelligence|contingency|"
        r"humantrafficking|overseas|response)",
        re.IGNORECASE,
    )

    entities = []
    seen = set()

    def add(name):
        name = name.strip().rstrip(".")
        if name and name not in seen and not BOILERPLATE.match(name):
            seen.add(name)
            entities.append(name)

    # Pattern 1: "(N) Company Name." — numbered list items
    for m in re.finditer(r"\(\d+\)\s+([A-Z][^\n]{3,100}?)\.", section_text):
        add(m.group(1))

    # Pattern 2: "(A) Company Name." — lettered list items
    if not entities:
        for m in re.finditer(r"\([A-Za-z]\)\s+([A-Z][^\n]{3,100}?)\.", section_text):
            add(m.group(1))

    # Pattern 3: ALL-CAPS or Title-Case company lines (typical in NDAA exhibits/tables)
    if not entities:
        for line in section_text.split("\n"):
            line = line.strip()
            # Must be a plausible company name: contains at least one space or known suffix,
            # is not pure boilerplate, and is not a short fragment
            if (len(line) > 5
                    and re.search(r"\b(Co\.|Corp\.|Ltd\.?|Inc\.?|LLC|Technologies?|Communications?|"
                                  r"Holdings?|Group|International|Systems?|Sciences?)\b", line, re.IGNORECASE)
                    and not BOILERPLATE.match(line)):
                add(line)

    return [
        {
            "entity_name": name,
            "aka": [],
            "country": "",
            "source_list": source_label,
            "list_category": list_category,
            "date_added": None,
            "federal_register_cite": pub_law,
            "notes": f"Extracted from {pub_law} PDF — verify against official statutory text",
        }
        for name in entities
    ]


def load_fallback(source_key):
    try:
        with open(FALLBACK_PATH) as f:
            all_fallback = json.load(f)
        label = NDAA_SOURCES[source_key]["label"]
        results = [e for e in all_fallback if e.get("source_list") == label]
        return results
    except Exception as e:
        print(f"  Could not load fallback: {e}")
        return []


def fetch():
    """
    Load NDAA entity lists from the curated fallback file.

    PDF parsing is skipped: neither § 5949 nor § 1260H contains a scrapable
    inline company list. § 5949 names SMIC, CXMT, and YMTC directly in the
    statute; § 1260H references the DoD annual Chinese military company list
    published separately. Both are maintained in references/ndaa_fallback.json.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = {}

    for key, cfg in NDAA_SOURCES.items():
        print(f"\n[NDAA {key.upper()}] Loading {cfg['label']} from fallback")
        out_path = os.path.join(OUTPUT_DIR, cfg["output_file"])

        entities = load_fallback(key)
        print(f"  Loaded {len(entities)} entities from references/ndaa_fallback.json")
        print(f"  Note: To update, edit references/ndaa_fallback.json directly.")

        with open(out_path, "w") as f:
            json.dump(entities, f, indent=2)
        print(f"  → {out_path}")
        results[key] = entities

    return results


if __name__ == "__main__":
    fetch()
