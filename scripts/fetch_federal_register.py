"""
fetch_federal_register.py
Queries the Federal Register API for notices citing NDAA § 1260H and § 5949
that may add entities mid-cycle (between statutory PDF publications).
Extracts any named entities from matching notices.
Outputs: output/raw/federal_register_ndaa.json
"""

import json
import os
import re
import requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "raw")

FR_API = "https://www.federalregister.gov/api/v1/documents.json"

# Search terms that reliably appear in FR notices adding entities to these lists
QUERIES = [
    {
        "label": "NDAA FY2021 § 1260H",
        "pub_law": "Pub. L. 116-283",
        "list_category": 2,
        "params": {
            "conditions[term]": "1260H",
            "conditions[agencies][]": "commerce-department",
            "per_page": 20,
            "order": "newest",
            "fields[]": ["title", "abstract", "full_text_xml_url", "publication_date", "citation"],
        },
    },
    {
        "label": "NDAA FY2023 § 5949",
        "pub_law": "Pub. L. 117-263",
        "list_category": 2,
        "params": {
            "conditions[term]": "5949 prohibited",
            "conditions[agencies][]": "commerce-department",
            "per_page": 20,
            "order": "newest",
            "fields[]": ["title", "abstract", "full_text_xml_url", "publication_date", "citation"],
        },
    },
    {
        "label": "NDAA FY2021 § 1260H",
        "pub_law": "Pub. L. 116-283",
        "list_category": 2,
        "params": {
            "conditions[term]": "1260H Chinese military",
            "conditions[agencies][]": "defense-department",
            "per_page": 20,
            "order": "newest",
            "fields[]": ["title", "abstract", "full_text_xml_url", "publication_date", "citation"],
        },
    },
]

# Regex patterns to extract company names from FR notice text
# FR notices typically list entities as: "Adding [Company Name] to the [List]"
# or in a table/list format
ENTITY_PATTERNS = [
    r"adding\s+([A-Z][A-Za-z0-9 &,\.\-]{3,80})\s+(?:to|of)\s+(?:the\s+)?(?:list|entity|covered)",
    r"^\s*[-•]\s*([A-Z][A-Za-z0-9 &,\.\-]{5,80})\s*$",
    r"\"([A-Z][A-Za-z0-9 &,\.\-]{5,80})\"",
    r"\b([A-Z][A-Za-z0-9]{2,}\s+(?:Co\.|Corp\.|Inc\.|Ltd\.|LLC|Group|Technologies|Technology|Systems|Holdings)[^\n]{0,40})",
]


TRUSTED_FR_DOMAINS = (
    "federalregister.gov",
    "www.federalregister.gov",
    "api.federalregister.gov",
    "ofr.gov",
    "www.ofr.gov",
)


def validate_fr_url(url):
    """Validate URL is HTTPS and from a trusted domain (CWE-918, CWE-311)."""
    if not url or not isinstance(url, str):
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return None
        if parsed.netloc not in TRUSTED_FR_DOMAINS:
            return None
        return url
    except Exception:
        return None


def fetch_notice_text(xml_url):
    """Fetch full text of a Federal Register notice."""
    safe_url = validate_fr_url(xml_url)
    if not safe_url:
        return ""
    try:
        r = requests.get(safe_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        # Strip XML tags for text extraction
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text)
        return text
    except Exception as e:
        print(f"    Could not fetch notice text: {e}")
        return ""


def extract_entities_from_text(text, source_label, pub_law, list_category, citation, pub_date):
    """Extract named entities from FR notice text using regex patterns."""
    entities = []
    seen = set()

    for pattern in ENTITY_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            name = match.strip().rstrip(".,;")
            # Filter out false positives: too short, all lowercase, looks like a sentence fragment
            if len(name) < 6:
                continue
            if name.lower() == name:
                continue
            if name in seen:
                continue
            # Skip common false positives
            if any(skip in name.lower() for skip in ["federal register", "commerce department", "bureau of industry", "united states", "executive order"]):
                continue
            seen.add(name)
            entities.append({
                "entity_name": name,
                "aka": [],
                "country": "",
                "source_list": source_label,
                "list_category": list_category,
                "date_added": pub_date,
                "federal_register_cite": citation,
                "notes": f"Extracted from Federal Register notice — {pub_law} mid-cycle addition. Manual review recommended.",
            })

    return entities


def fetch():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_entities = []
    seen_citations = set()

    for query_cfg in QUERIES:
        label = query_cfg["label"]
        print(f"\n[FedReg] Querying for {label}: '{query_cfg['params'].get('conditions[term]', '')}'")

        try:
            r = requests.get(FR_API, params=query_cfg["params"], timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[FedReg] API request failed: {e}")
            continue

        results = data.get("results", [])
        print(f"[FedReg] Found {len(results)} notices")

        for notice in results:
            title = notice.get("title", "")
            citation = notice.get("citation", "")
            pub_date = notice.get("publication_date", "")
            xml_url = notice.get("full_text_xml_url", "")
            abstract = notice.get("abstract", "") or ""

            # Skip duplicates across queries
            if citation in seen_citations:
                continue
            seen_citations.add(citation)

            # Filter: only process notices that are clearly about entity list additions
            combined = f"{title} {abstract}".lower()
            if not any(kw in combined for kw in ["entit", "prohibit", "list", "compan", "1260", "5949"]):
                continue

            print(f"  Processing: {title[:70]} ({pub_date})")

            # Try abstract first (faster), fall back to full text
            entities = extract_entities_from_text(
                abstract, query_cfg["label"], query_cfg["pub_law"],
                query_cfg["list_category"], citation, pub_date
            )

            if not entities and xml_url:
                full_text = fetch_notice_text(xml_url)
                entities = extract_entities_from_text(
                    full_text, query_cfg["label"], query_cfg["pub_law"],
                    query_cfg["list_category"], citation, pub_date
                )

            if entities:
                print(f"    Extracted {len(entities)} candidate entities")
                all_entities.extend(entities)
            else:
                print(f"    No entities extracted (notice may be procedural)")

    if all_entities:
        print(f"\n[FedReg] *** {len(all_entities)} candidate entities from Federal Register — MANUAL REVIEW REQUIRED ***")
        print("[FedReg] Regex extraction from legal text is imprecise. Verify each entry against the original notice.")

    out = os.path.join(OUTPUT_DIR, "federal_register_ndaa.json")
    with open(out, "w") as f:
        json.dump(all_entities, f, indent=2)
    print(f"[FedReg] {len(all_entities)} entities → {out}")
    return all_entities


if __name__ == "__main__":
    fetch()
