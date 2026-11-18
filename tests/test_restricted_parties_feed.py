"""
Tests for the us-restricted-parties feed fallback. They use small local release
files (with a manifest.json carrying their SHA-256), so they need no network.

    python -m unittest discover -s tests
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)

import restricted_parties_feed  # noqa: E402
import us_restricted_parties  # noqa: E402

FR_1260H = ("https://www.federalregister.gov/documents/2026/06/10/2026-11571/"
            "notice-of-availability-of-designation-of-chinese-military-companies")
FR_UFLPA = ("https://www.federalregister.gov/documents/2026/10/29/2026-22094/"
            "notice-regarding-the-uyghur-forced-labor-prevention-act-entity-list")
CETC = "us_dod_1260h-china-electronics-technology-group-corporation"

# Records as they appear in the data-2026-11-18 release (fields trimmed).
RECORDS = {
    "us_dod_1260h": [
        {"DATA_SOURCE": "US_DOD_1260H", "RECORD_ID": CETC,
         "NAME_ORG": "China Electronics Technology Group Corporation",
         "NAMES": [{"NAME_TYPE": "PRIMARY", "NAME_ORG": "China Electronics Technology Group Corporation"},
                   {"NAME_TYPE": "ALIAS", "NAME_ORG": "CETC"}],
         "LISTED_ON": "2026-06-10", "SOURCE_URL": FR_1260H, "SOURCE_DOC": "2026-11571"},
        {"DATA_SOURCE": "US_DOD_1260H", "RECORD_ID": "us_dod_1260h-14th-research-institute-of-cetc",
         "NAME_ORG": "14th Research Institute of CETC",
         "NAMES": [{"NAME_TYPE": "PRIMARY", "NAME_ORG": "14th Research Institute of CETC"}],
         "LISTED_ON": "2026-06-10", "SOURCE_URL": FR_1260H, "SOURCE_DOC": "2026-11571",
         "PARENT_NAME": "China Electronics Technology Group Corporation",
         "RELATIONSHIPS": [{"REL_POINTER_DOMAIN": "US_DOD_1260H", "REL_POINTER_KEY": CETC,
                            "REL_POINTER_ROLE": "SUBSIDIARY_OF"}]},
    ],
    "us_fcc_covered": [
        {"DATA_SOURCE": "US_FCC_COVERED", "RECORD_ID": "us_fcc_covered-digitalsystem-technology-inc",
         "NAME_ORG": "Digitalsystem Technology Inc",
         "NAMES": [{"NAME_TYPE": "PRIMARY", "NAME_ORG": "Digitalsystem Technology Inc"}],
         "LISTED_ON": "2026-07-07", "SOURCE_URL": "https://www.fcc.gov/supplychain/coveredlist",
         "SOURCE_DOC": "International telecommunications services provided by Digitalsystem Technology "
                       "Inc., subject to section 214 of the Communications Act of 1934."},
    ],
    "us_dhs_uflpa": [
        {"DATA_SOURCE": "US_DHS_UFLPA", "RECORD_ID": "us_dhs_uflpa-xinjiang-production-and-construction-corps",
         "NAME_ORG": "Xinjiang Production and Construction Corps",
         "NAMES": [{"NAME_TYPE": "PRIMARY", "NAME_ORG": "Xinjiang Production and Construction Corps"},
                   {"NAME_TYPE": "ALIAS", "NAME_ORG": "XPCC"},
                   {"NAME_TYPE": "ALIAS", "NAME_ORG": "Bingtuan"}],
         "LISTED_ON": "2022-06-21", "SOURCE_URL": FR_UFLPA, "SOURCE_DOC": "2026-22094",
         "INCLUDES_AFFILIATES": True},
    ],
}


class FeedFixture(unittest.TestCase):
    """Writes the records above as a release directory and points the feed at it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.release_dir = os.path.join(self.tmp, "release")
        self.out_dir = os.path.join(self.tmp, "raw")
        os.makedirs(self.release_dir)
        os.makedirs(self.out_dir)
        manifest = {"lists": {}}
        for name, records in RECORDS.items():
            data = "".join(json.dumps(r) + "\n" for r in records).encode("utf-8")
            with open(os.path.join(self.release_dir, name + ".jsonl"), "wb") as f:
                f.write(data)
            manifest["lists"][name] = {"sha256": hashlib.sha256(data).hexdigest()}
        with open(os.path.join(self.release_dir, "manifest.json"), "w") as f:
            json.dump(manifest, f)

        real_load = us_restricted_parties.load

        def local_load(list_name, source=None, release=None, verify=False):
            return real_load(list_name, source=os.path.join(self.release_dir, list_name + ".jsonl"),
                             verify=verify)

        patcher = mock.patch.object(restricted_parties_feed, "load", local_load)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def read_output(self, file_name):
        with open(os.path.join(self.out_dir, file_name), encoding="utf-8") as f:
            return json.load(f)


class TestFetchList(FeedFixture):
    def test_1260h_parent_and_named_subsidiary(self):
        entities = restricted_parties_feed.fetch_list(
            "us_dod_1260h", "NDAA FY2021 § 1260H", 2, country="China")
        self.assertEqual([e["entity_name"] for e in entities],
                         ["China Electronics Technology Group Corporation", "14th Research Institute of CETC"])
        parent, sub = entities
        self.assertEqual(parent["aka"], ["CETC"])
        self.assertEqual(parent["federal_register_cite"], "FR Doc. 2026-11571")
        self.assertEqual(parent["date_added"], "2026-06-10")
        self.assertEqual(parent["country"], "China")
        self.assertIn("Subsidiary of China Electronics Technology Group Corporation", sub["notes"])
        self.assertIn("us-restricted-parties", sub["notes"])

    def test_covered_list_description_kept_in_notes(self):
        (entity,) = restricted_parties_feed.fetch_list("us_fcc_covered", "FCC Covered List", 1)
        self.assertIsNone(entity["federal_register_cite"])
        self.assertTrue(entity["notes"].startswith("International telecommunications services"))

    def test_hash_mismatch_returns_nothing(self):
        path = os.path.join(self.release_dir, "us_dhs_uflpa.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"DATA_SOURCE": "US_DHS_UFLPA", "NAME_ORG": "Tampered Co."}) + "\n")
        self.assertEqual(restricted_parties_feed.fetch_list("us_dhs_uflpa", "DHS UFLPA Entity List", 2), [])


class TestFetchers(FeedFixture):
    def test_ndaa_1260h_on_a_clean_checkout(self):
        import fetch_ndaa_lists
        missing = os.path.join(self.tmp, "ndaa_fallback.json")
        with mock.patch.object(fetch_ndaa_lists, "FALLBACK_PATH", missing), \
                mock.patch.object(fetch_ndaa_lists, "OUTPUT_DIR", self.out_dir):
            fetch_ndaa_lists.fetch()
        names = [e["entity_name"] for e in self.read_output("ndaa_1260h.json")]
        self.assertEqual(len(names), 2)  # was 0 without references/ndaa_fallback.json
        self.assertEqual(self.read_output("ndaa_1260h.json")[0]["source_list"], "NDAA FY2021 § 1260H")

    def test_ndaa_local_file_still_wins(self):
        import fetch_ndaa_lists
        local = os.path.join(self.tmp, "ndaa_fallback.json")
        with open(local, "w", encoding="utf-8") as f:
            json.dump([{"entity_name": "Local Entry Co.", "source_list": "NDAA FY2021 § 1260H"}], f)
        with mock.patch.object(fetch_ndaa_lists, "FALLBACK_PATH", local), \
                mock.patch.object(fetch_ndaa_lists, "OUTPUT_DIR", self.out_dir):
            fetch_ndaa_lists.fetch()
        self.assertEqual([e["entity_name"] for e in self.read_output("ndaa_1260h.json")], ["Local Entry Co."])

    def test_covered_list_uses_feed_before_hardcoded(self):
        import fetch_covered_list
        with mock.patch.object(fetch_covered_list.requests.Session, "get", side_effect=OSError("403")), \
                mock.patch.object(fetch_covered_list, "OUTPUT_DIR", self.out_dir):
            fetch_covered_list.fetch()
        out = self.read_output("covered_list.json")
        self.assertEqual([e["entity_name"] for e in out], ["Digitalsystem Technology Inc"])
        self.assertFalse(out[0]["conditional_approval"])

    def test_uflpa_when_dhs_is_unreachable(self):
        import fetch_uflpa
        with mock.patch.object(fetch_uflpa.requests, "get", side_effect=OSError("403 Forbidden")), \
                mock.patch.object(fetch_uflpa, "OUTPUT_DIR", self.out_dir):
            fetch_uflpa.fetch()
        (entity,) = self.read_output("uflpa.json")  # was [] when dhs.gov failed
        self.assertEqual(entity["aka"], ["XPCC", "Bingtuan"])
        self.assertEqual(entity["country"], "CN")
        self.assertIn("also covers subsidiaries or affiliates", entity["notes"])


if __name__ == "__main__":
    unittest.main()
