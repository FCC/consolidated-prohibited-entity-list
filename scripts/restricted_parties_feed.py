"""
restricted_parties_feed.py
Reads source lists from the us-restricted-parties feed
(https://github.com/Mattbusel/us-restricted-parties) and maps the records to the
schema used by compile_master_list.py.

The feed is rebuilt daily from the agency sources: the Federal Register notices for
§ 1260H and the UFLPA Entity List, and fcc.gov for the Covered List. Every data
release is kept, and each file is checked against the SHA-256 in that release's
manifest.json before it is used, so a pinned release always gives the same records.

The fetch scripts use it where they otherwise have nothing:
  fetch_ndaa_lists.py    § 1260H, when references/ndaa_fallback.json has no entries
  fetch_covered_list.py  before the hardcoded fallback
  fetch_uflpa.py         when dhs.gov cannot be fetched or returns no entities

Set US_RESTRICTED_PARTIES_RELEASE to another data release tag, or to "latest", to
read a different release. us_restricted_parties.py is tools/load.py from that
repository at v0.5.0, copied unchanged (MIT license, standard library only).
"""

import os
import re

from us_restricted_parties import load, names

FEED_URL = "https://github.com/Mattbusel/us-restricted-parties"
RELEASE = os.environ.get("US_RESTRICTED_PARTIES_RELEASE", "data-2026-11-18")

FR_DOC = re.compile(r"^\d{4}-\d{4,5}$")


def fetch_list(list_name, source_list, list_category, country="", source=None):
    """
    Records of one feed list ("us_dod_1260h", "us_fcc_covered", "us_dhs_uflpa") in
    this repository's schema. Returns [] when the release cannot be read or a file
    does not match its SHA-256, so callers can fall back as before.

    source: optional local path to the list file (with manifest.json next to it).
    """
    release = None if RELEASE == "latest" else RELEASE
    try:
        records = load(list_name, source=source, release=release, verify=True)
    except Exception as e:
        print(f"  us-restricted-parties feed unavailable ({list_name}, {RELEASE}): {e}")
        return []

    entities = []
    for r in records:
        doc = r.get("SOURCE_DOC") or ""
        notes = []
        if r.get("PARENT_NAME"):
            notes.append(f"Subsidiary of {r['PARENT_NAME']}, named in the listing.")
        if r.get("INCLUDES_AFFILIATES"):
            notes.append("The listing also covers subsidiaries or affiliates.")
        if doc and not FR_DOC.match(doc):
            notes.append(doc)  # Covered List: the FCC's description of the covered equipment or service
        notes.append(f"From us-restricted-parties {RELEASE} ({FEED_URL}); "
                     f"verify at {r.get('SOURCE_URL', '')}")
        entities.append({
            "entity_name": r["NAME_ORG"],
            "aka": names(r)[1:],
            "country": country,
            "source_list": source_list,
            "list_category": list_category,
            "date_added": r.get("LISTED_ON"),
            "federal_register_cite": f"FR Doc. {doc}" if FR_DOC.match(doc) else None,
            "notes": " ".join(notes),
        })
    return entities


def _keys(entity):
    return {re.sub(r"[^a-z0-9]", "", n.lower())
            for n in [entity.get("entity_name", "")] + list(entity.get("aka") or []) if n}


def report_differences(label, local, feed):
    """Print the names on only one side, when a local list is used and the feed is the cross-check."""
    if not feed:
        return
    local_keys = set().union(*(_keys(e) for e in local)) if local else set()
    feed_keys = set().union(*(_keys(e) for e in feed))
    only_feed = [e["entity_name"] for e in feed if not _keys(e) & local_keys]
    only_local = [e["entity_name"] for e in local if not _keys(e) & feed_keys]
    print(f"  Cross-check against us-restricted-parties {RELEASE}: "
          f"{len(only_feed)} only in the feed, {len(only_local)} only in the local list")
    for name in only_feed:
        print(f"    feed only:  {name}")
    for name in only_local:
        print(f"    local only: {name}")
