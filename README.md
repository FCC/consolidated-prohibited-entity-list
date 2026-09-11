# FCC Prohibited Entities Consolidation Scripts

This repository contains the scripts used to compile a consolidated list of entities prohibited under **47 CFR § 2.902** of the Commission's rules. The output supports the equipment authorization integrity measures adopted in the Second Report and Order in ET Docket No. 24-136 (the Second EA Integrity R&O), which directed the Office of Engineering and Technology (OET) to publish a consolidated prohibited entities list for public use.

The consolidated list itself is published at [fcc.gov/engineering-technology/prohibited-entities-list](https://www.fcc.gov/engineering-technology/prohibited-entities-list). See the public notice, [DA-26-962](https://docs.fcc.gov/public/attachments/DA-26-962A1.pdf), for background on the underlying rulemaking and the reason this list was created.

## What this does

Section 2.902 defines a "Prohibited Entity" by reference to lists housed with multiple different agencies. Per the public notice linked above, multiple commenters reported challenges identifying whether an entity is prohibited because of this. These scripts fetch each source list below, normalize them into a common schema, deduplicate overlapping entries, and compile a single dated CSV and JSON output.

### Source lists

| # | List | Authority | Script |
|---|------|-----------|--------|
| 1 | FCC Covered List | 47 CFR § 1.50002 | `fetch_covered_list.py` |
| 2 | BIS Entity List | 15 CFR Part 744, Supp. 4 | `fetch_bis_entity_list.py` |
| 3 | BIS Military End-User (MEU) List | 15 CFR Part 744, Supp. 7 | `fetch_bis_entity_list.py` |
| 4 | DHS UFLPA Entity List | 19 U.S.C. § 4681 | `fetch_uflpa.py` |
| 5 | NDAA FY2023 § 5949 | Pub. L. 117-263 | `fetch_ndaa_lists.py` |
| 6 | NDAA FY2021 § 1260H | Pub. L. 116-283 | `fetch_ndaa_lists.py` |
| 7 | Treasury NS-CMIC List | 31 CFR Part 586 | `fetch_treasury_ns_cmic.py` |
| 8 | Foreign Adversaries | 15 CFR § 791.4 | `fetch_foreign_adversaries.py` |

`fetch_federal_register.py` is also included as a supplemental script that queries the Federal Register API for Commerce and Defense notices citing §§ 1260H and 5949. Its output is a set of leads for manual review, not a confirmed source list.

### Scope note

These scripts compile the *named* entities on each source list. They do not perform affiliate or subsidiary screening under the 10 percent ownership and control test in § 2.902's definition of "owned by, controlled by, or subject to the direction of." Identifying affiliates and subsidiaries requires a separate screening workflow against a corporate ownership database and is outside the scope of this repository.

## Usage

Install dependencies:

```bash
pip install requests beautifulsoup4 pandas pdfplumber lxml rapidfuzz
```

Run each fetcher, then compile the master list:

```bash
cd scripts

python fetch_covered_list.py
python fetch_bis_entity_list.py
python fetch_uflpa.py
python fetch_ndaa_lists.py
python fetch_federal_register.py
python fetch_treasury_ns_cmic.py
python fetch_foreign_adversaries.py

python compile_master_list.py
```

Each fetcher writes a normalized JSON file to `output/raw/`. `compile_master_list.py` reads everything in `output/raw/`, deduplicates by normalized entity name and country using fuzzy matching, and writes:

- `output/prohibited_entities_YYYYMMDD.csv`
- `output/prohibited_entities_YYYYMMDD.json`

### Output schema

`entity_name | aka | country | source_list | list_category | date_added | federal_register_cite | notes | compiled_date`

## Known limitations

- **FCC Covered List and Treasury NS-CMIC List** are served in ways that resist reliable scraping (client-side rendering and a retired XML endpoint, respectively). Both scripts fall back to a hardcoded list embedded in the script itself when the live fetch fails. These hardcoded fallbacks require manual review and update whenever the source agency amends its list. See the comments in `fetch_covered_list.py` and `fetch_treasury_ns_cmic.py` for details and current verification links.
- **NDAA §§ 5949 and 1260H** are extracted from the underlying statutory PDF text. PDF parsing of legal text is imperfect. A manually curated fallback snapshot is bundled at `references/ndaa_fallback.json` and is used if parsing returns zero results.
- **Federal Register extraction** uses regex against notice text and should be treated as leads to verify, not confirmed entries.

Given these limitations, users are responsible for verifying the accuracy of any output produced by these scripts against the original source list published by the responsible agency. This repository is not the authoritative FCC list. The authoritative, regularly updated consolidated list is maintained at [fcc.gov/engineering-technology/prohibited-entities-list](https://www.fcc.gov/engineering-technology/prohibited-entities-list).

## Source list references

Direct links to each source list are maintained in `references/source_urls.md`.

## Contact

As listed in the public notice, DA-26-962:

For further information, contact Erika Heeren-Moon, Fellow, Project CYPHER (Cybersecurity and Privacy Harnessing Engineering & Research), Office of Engineering and Technology, by email at erika.heeren@fcc.gov, with a copy to OET-NatSec@fcc.gov, or by phone at (202) 418-7552.
