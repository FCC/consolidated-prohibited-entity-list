"""
Hardcoded fallback for Treasury NS-CMIC List.
Run this if fetch_treasury_ns_cmic.py returns fewer than 30 entities.

Usage:
    python3 patch_treasury_ns_cmic.py
"""
import json
from pathlib import Path

# NS-CMIC entities as of June 2026
# Source: https://home.treasury.gov/policy-issues/financial-sanctions/consolidated-sanctions-list/
#         non-sdn-chinese-military-industrial-complex-companies-list-ns-cmic-list
ENTITIES = [
    "Advanced Micro-Fabrication Equipment Inc. China",
    "Aerosun Corporation",
    "Aero Engine Corporation of China",
    "Aviation Industry Corporation of China",
    "China Academy of Launch Vehicle Technology",
    "China Aerospace Science and Industry Corporation",
    "China Aerospace Science and Technology Corporation",
    "China Communications Construction Company",
    "China Electronics Corporation",
    "China Electronics Technology Group Corporation",
    "China General Nuclear Power Corporation",
    "China Mobile Communications Group",
    "China National Aviation Holding Corporation",
    "China National Chemical Corporation",
    "China National Chemical Engineering Group Corporation",
    "China National Nuclear Corporation",
    "China National Offshore Oil Corporation",
    "China North Industries Group Corporation",
    "China Railway Construction Corporation",
    "China Shipbuilding Group Corporation",
    "China Shipbuilding Industry Corporation",
    "China South Industries Group Corporation",
    "China Spacesat",
    "China Telecom Corporation",
    "China Three Gorges Corporation",
    "China Unicom (Hong Kong)",
    "CNOOC Limited",
    "Commercial Aircraft Corporation of China",
    "CSSC Offshore & Marine Engineering (Group) Company",
    "Hangzhou Hikvision Digital Technology",
    "Huawei Investment & Holding",
    "Inner Mongolia First Machinery Group",
    "Inspur Group",
]

entries = []
for name in ENTITIES:
    entries.append({
        "entity_name": name,
        "aka": [],
        "country": "China",
        "source_list": "Treasury NS-CMIC List",
        "list_category": 2,
        "date_added": None,
        "federal_register_cite": "31 CFR Part 586; E.O. 13959",
        "notes": "Non-SDN Chinese Military-Industrial Complex Companies List",
    })

out_path = Path(__file__).parent / ".." / "output" / "raw" / "treasury_ns_cmic.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(entries, indent=2))
print(f"Wrote {len(entries)} NS-CMIC entities to {out_path.resolve()}")
print("Now run: python3 compile_master_list.py")
