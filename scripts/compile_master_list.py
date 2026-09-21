"""
compile_master_list.py
Reads all output/raw/*.json files, deduplicates (with fuzzy matching), and compiles
the master prohibited entities list as both CSV and JSON.

Outputs:
  output/prohibited_entities_YYYYMMDD.csv
  output/prohibited_entities_YYYYMMDD.json
  output/run_summary.txt
  output/changes_YYYYMMDD.csv  (only when --diff is passed)

Usage:
  python compile_master_list.py           # standard compile
  python compile_master_list.py --diff    # compile + diff against last snapshot
"""

import csv
import json
import os
import re
import sys
from datetime import date
from glob import glob

try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    print("WARNING: rapidfuzz not installed. Falling back to exact dedup.")
    print("Install with: pip install rapidfuzz --break-system-packages")

SCRIPT_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(SCRIPT_DIR, "..", "output", "raw")
OUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")

FUZZY_THRESHOLD = 92  # minimum similarity score (0-100) to treat as duplicate

FIELDS = [
    "entity_name",
    "aka",
    "country",
    "source_list",
    "list_category",
    "date_added",
    "federal_register_cite",
    "notes",
    "compiled_date",
]

CATEGORY_LABELS = {
    1: "FCC Covered List (§ 1.50002)",
    2: "Statutory Source List (§ 2.902(2))",
    3: "Foreign Adversary (§ 2.902(3))",
}

DIFF_FIELDS = ["entity_name", "country", "source_list", "change_type", "compiled_date"]


def normalize_name(name):
    """Normalize entity name for comparison."""
    name = name.lower().strip()
    name = re.sub(r"[,\.;:()\-]", " ", name)
    name = re.sub(r"\b(co|corp|inc|ltd|llc|the|and|of|a)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def load_all_raw():
    """Load all raw JSON files from output/raw/."""
    all_entities = []
    raw_files = sorted(glob(os.path.join(RAW_DIR, "*.json")))

    if not raw_files:
        print(f"ERROR: No raw files found in {RAW_DIR}")
        print("Run the individual fetch_*.py scripts first.")
        sys.exit(1)

    source_counts = {}
    for path in raw_files:
        fname = os.path.basename(path)
        # CWE-73: Validate path is inside expected RAW_DIR before opening
        resolved = os.path.realpath(path)
        expected_dir = os.path.realpath(RAW_DIR)
        if not resolved.startswith(expected_dir + os.sep):
            print(f"  WARNING: Skipping {fname} -- path outside expected directory")
            continue
        try:
            with open(resolved, encoding="utf-8") as f:
                data = json.load(f)
            count = len(data)
            flag = " *** 0 ENTITIES — FETCH MAY HAVE FAILED ***" if count == 0 else ""
            print(f"  Loaded {count:>5} entities from {fname}{flag}")
            all_entities.extend(data)
            if data:
                src = data[0].get("source_list", fname)
                source_counts[src] = source_counts.get(src, 0) + count
            else:
                source_counts[fname] = 0
        except Exception as e:
            print(f"  WARNING: Could not load {fname}: {e}")

    return all_entities, source_counts


def merge_into(existing, new_entity):
    """Merge a duplicate entity's metadata into the existing record."""
    new_source = new_entity.get("source_list", "")
    if new_source and new_source not in existing["source_list"]:
        existing["source_list"] = f"{existing['source_list']}; {new_source}"

    existing_akas = set(existing.get("aka") or [])
    new_akas = set(new_entity.get("aka") or [])
    existing["aka"] = sorted(existing_akas | new_akas)

    # Keep earliest date_added
    if new_entity.get("date_added") and not existing.get("date_added"):
        existing["date_added"] = new_entity["date_added"]


def deduplicate_exact(entities):
    """Fast exact dedup by normalized name + country."""
    seen = {}
    deduped = []

    for entity in entities:
        name = entity.get("entity_name", "").strip()
        country = entity.get("country", "").strip()
        key = (normalize_name(name), country.lower())

        if key in seen:
            merge_into(deduped[seen[key]], entity)
        else:
            seen[key] = len(deduped)
            deduped.append(dict(entity))

    return deduped


def deduplicate_fuzzy(entities):
    """
    Two-pass dedup:
      Pass 1: exact key match (fast)
      Pass 2: rapidfuzz near-match within same country (catches name variants)
    """
    # Pass 1
    deduped = deduplicate_exact(entities)
    print(f"  After exact dedup: {len(deduped)}")

    # Pass 2: fuzzy within country groups
    by_country = {}
    for i, e in enumerate(deduped):
        c = e.get("country", "").lower()
        by_country.setdefault(c, []).append(i)

    merged = set()
    fuzzy_merge_count = 0

    for country, indices in by_country.items():
        if len(indices) < 2:
            continue
        names = [(i, normalize_name(deduped[i].get("entity_name", ""))) for i in indices]

        for j, (i, norm_name) in enumerate(names):
            if i in merged:
                continue
            for i2, norm_name2 in names[j+1:]:
                if i2 in merged:
                    continue
                score = fuzz.token_sort_ratio(norm_name, norm_name2)
                if score >= FUZZY_THRESHOLD:
                    merge_into(deduped[i], deduped[i2])
                    merged.add(i2)
                    fuzzy_merge_count += 1

    result = [e for i, e in enumerate(deduped) if i not in merged]
    print(f"  After fuzzy dedup (threshold={FUZZY_THRESHOLD}): {len(result)} ({fuzzy_merge_count} fuzzy merges)")
    return result


def deduplicate(entities):
    if FUZZY_AVAILABLE:
        return deduplicate_fuzzy(entities)
    else:
        result = deduplicate_exact(entities)
        print(f"  After exact dedup: {len(result)}")
        return result


def find_last_snapshot():
    """Find the most recent prior output JSON to diff against."""
    today = date.today().strftime("%Y%m%d")
    snapshots = sorted(glob(os.path.join(OUT_DIR, "prohibited_entities_????????.json")))
    prior = [s for s in snapshots if f"prohibited_entities_{today}.json" not in s]
    return prior[-1] if prior else None


def compute_diff(current_entities, prior_path, compiled_date):
    """Compare current list against prior snapshot."""
    # CWE-73: Validate prior_path is inside expected OUT_DIR before opening
    resolved_prior = os.path.realpath(prior_path)
    expected_out = os.path.realpath(OUT_DIR)
    if not resolved_prior.startswith(expected_out + os.sep):
        print("  WARNING: Prior snapshot path outside expected directory -- skipping diff")
        return []
    try:
        with open(resolved_prior) as f:
            prior = json.load(f)
    except Exception as e:
        print(f"  WARNING: Could not load prior snapshot: {e}")
        return []

    prior_keys = {
        (normalize_name(e.get("entity_name", "")), e.get("country", "").lower()): e
        for e in prior
    }
    current_keys = {
        (normalize_name(e.get("entity_name", "")), e.get("country", "").lower()): e
        for e in current_entities
    }

    changes = []
    for key, e in current_keys.items():
        if key not in prior_keys:
            changes.append({
                "entity_name": e.get("entity_name", ""),
                "country": e.get("country", ""),
                "source_list": e.get("source_list", ""),
                "change_type": "ADDED",
                "compiled_date": compiled_date,
            })

    for key, e in prior_keys.items():
        if key not in current_keys:
            changes.append({
                "entity_name": e.get("entity_name", ""),
                "country": e.get("country", ""),
                "source_list": e.get("source_list", ""),
                "change_type": "REMOVED",
                "compiled_date": compiled_date,
            })

    return changes


def compile_master_list(run_diff=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    compiled_date = date.today().isoformat()

    print("\n=== Loading raw source files ===")
    all_entities, source_counts = load_all_raw()
    print(f"\nTotal before dedup: {len(all_entities)}")

    print("\n=== Deduplicating ===")
    deduped = deduplicate(all_entities)
    print(f"Final total:        {len(deduped)}")

    # Add compiled_date, normalize aka for CSV, add category label
    for e in deduped:
        e["compiled_date"] = compiled_date
        if isinstance(e.get("aka"), list):
            e["aka"] = "; ".join(e["aka"])
        e["list_category_label"] = CATEGORY_LABELS.get(e.get("list_category"), "")

    # Sort: by category, then country, then name
    deduped.sort(key=lambda e: (
        e.get("list_category", 9),
        e.get("country", ""),
        e.get("entity_name", "").lower(),
    ))

    # Write CSV
    csv_path = os.path.join(OUT_DIR, f"prohibited_entities_{today}.csv")
    csv_fields = FIELDS + ["list_category_label"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(deduped)
    print(f"\n→ CSV:  {csv_path}")

    # Write JSON
    json_path = os.path.join(OUT_DIR, f"prohibited_entities_{today}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)
    print(f"→ JSON: {json_path}")

    # Build summary
    summary_lines = [
        "FCC § 2.902 Prohibited Entities Master List",
        f"Compiled: {compiled_date}",
        f"Fuzzy dedup: {'enabled (rapidfuzz)' if FUZZY_AVAILABLE else 'disabled — install rapidfuzz'}",
        "",
        f"Total entities (deduplicated): {len(deduped)}",
        "",
        "By source (raw counts before dedup):",
    ]
    for src, count in sorted(source_counts.items()):
        flag = " *** 0 ENTITIES — FETCH MAY HAVE FAILED ***" if count == 0 else ""
        summary_lines.append(f"  {src}: {count}{flag}")

    # Diff
    diff_path = None
    if run_diff:
        print("\n=== Computing diff against last snapshot ===")
        prior_path = find_last_snapshot()
        if prior_path:
            print(f"  Comparing against: {os.path.basename(prior_path)}")
            changes = compute_diff(deduped, prior_path, compiled_date)
            added = [c for c in changes if c["change_type"] == "ADDED"]
            removed = [c for c in changes if c["change_type"] == "REMOVED"]
            print(f"  Added:   {len(added)}")
            print(f"  Removed: {len(removed)}")

            diff_path = os.path.join(OUT_DIR, f"changes_{today}.csv")
            with open(diff_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=DIFF_FIELDS)
                writer.writeheader()
                writer.writerows(sorted(changes, key=lambda c: (c["change_type"], c["entity_name"])))
            print(f"→ Diff: {diff_path}")

            summary_lines += [
                "",
                f"Changes vs {os.path.basename(prior_path)}:",
                f"  Added:   {len(added)}",
                f"  Removed: {len(removed)}",
                f"  Diff file: changes_{today}.csv",
            ]
        else:
            print("  No prior snapshot found — skipping diff")
            summary_lines.append("\nDiff requested but no prior snapshot found.")

    # Write summary
    summary_path = os.path.join(OUT_DIR, "run_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(summary_lines))

    print(f"\n=== Run Summary ===")
    print("\n".join(summary_lines))

    return csv_path, json_path, diff_path


if __name__ == "__main__":
    run_diff = "--diff" in sys.argv
    compile_master_list(run_diff=run_diff)
