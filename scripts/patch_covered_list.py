"""
Run this from inside fcc-prohibited-entities/scripts/ to populate
the covered list from manually copied FCC data.

Usage:
    python3 patch_covered_list.py
"""
import json
from pathlib import Path

entries = [
    {"name": "Huawei Technologies Company", "description": "Telecommunications equipment produced by Huawei Technologies Company, including telecommunications or video surveillance services provided by such entity or using such equipment.", "effective_date": "2021-03-12"},
    {"name": "ZTE Corporation", "description": "Telecommunications equipment produced by ZTE Corporation, including telecommunications or video surveillance services provided by such entity or using such equipment.", "effective_date": "2021-03-12"},
    {"name": "Hytera Communications Corporation", "description": "Video surveillance and telecommunications equipment produced by Hytera Communications Corporation, to the extent it is used for the purpose of public safety, security of government facilities, physical security surveillance of critical infrastructure, and other national security purposes.", "effective_date": "2021-03-12"},
    {"name": "Hangzhou Hikvision Digital Technology Company", "description": "Video surveillance and telecommunications equipment produced by Hangzhou Hikvision Digital Technology Company, to the extent it is used for the purpose of public safety, security of government facilities, physical security surveillance of critical infrastructure, and other national security purposes.", "effective_date": "2021-03-12"},
    {"name": "Dahua Technology Company", "description": "Video surveillance and telecommunications equipment produced by Dahua Technology Company, to the extent it is used for the purpose of public safety, security of government facilities, physical security surveillance of critical infrastructure, and other national security purposes.", "effective_date": "2021-03-12"},
    {"name": "AO Kaspersky Lab", "description": "Information security products, solutions, and services supplied, directly or indirectly, by AO Kaspersky Lab or any of its predecessors, successors, parents, subsidiaries, or affiliates.", "effective_date": "2022-03-25"},
    {"name": "China Mobile International USA Inc.", "description": "International telecommunications services provided by China Mobile International USA Inc. subject to section 214 of the Communications Act of 1934.", "effective_date": "2022-03-25"},
    {"name": "China Telecom (Americas) Corp.", "description": "Telecommunications services provided by China Telecom (Americas) Corp. subject to section 214 of the Communications Act of 1934.", "effective_date": "2022-03-25"},
    {"name": "Pacific Networks Corp", "description": "International telecommunications services provided by Pacific Networks Corp and its wholly-owned subsidiary ComNet (USA) LLC subject to section 214 of the Communications Act of 1934.", "effective_date": "2022-09-20"},
    {"name": "ComNet (USA) LLC", "description": "International telecommunications services provided by ComNet (USA) LLC (wholly-owned subsidiary of Pacific Networks Corp) subject to section 214 of the Communications Act of 1934.", "effective_date": "2022-09-20"},
    {"name": "China Unicom (Americas) Operations Limited", "description": "International telecommunications services provided by China Unicom (Americas) Operations Limited subject to section 214 of the Communications Act of 1934.", "effective_date": "2022-09-20"},
    {"name": "Kaspersky Lab, Inc.", "description": "Cybersecurity and anti-virus software produced or provided by Kaspersky Lab, Inc. or any of its successors and assignees, including equipment with integrated Kaspersky Lab, Inc. cybersecurity or anti-virus software.", "effective_date": "2024-07-23"},
    {"name": "Foreign-produced Uncrewed Aircraft Systems (UAS)", "description": "Uncrewed aircraft systems (UAS) and UAS critical components produced in a foreign country, with exceptions for DCMA Blue UAS Cleared List, Buy American Standard domestic end products (until 2027-01-01), and devices with Conditional Approval by DoD or DHS. Also covers all communications and video surveillance equipment and services listed in Section 1709(a)(1) of the FY25 NDAA (Pub. L. 118-159).", "effective_date": "2025-12-22"},
    {"name": "Foreign-produced Routers", "description": "Routers produced in a foreign country, except routers which have been granted a Conditional Approval by DoD or DHS.", "effective_date": "2026-03-23"},
]

for e in entries:
    # Remap fields to match compile_master_list.py schema
    e["entity_name"] = e.pop("name")
    e["aka"] = []
    e["source_list"] = "FCC Covered List (§ 2.902)"
    e["list_category"] = 1
    e["date_added"] = e.pop("effective_date", None)
    e["federal_register_cite"] = None
    e["notes"] = e.pop("description", "")
    e.pop("source", None)
    e["country"] = e.pop("country", "")

out_path = Path(__file__).parent / ".." / "output" / "raw" / "covered_list.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(entries, indent=2))
print(f"Wrote {len(entries)} entries to {out_path.resolve()}")
print("Now run: python3 compile_master_list.py")
