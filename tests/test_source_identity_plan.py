from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "zotero-librarian" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "source_identity_plan.py"
SPEC = importlib.util.spec_from_file_location("source_identity_plan", SCRIPT)
assert SPEC and SPEC.loader
plan_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plan_module
SPEC.loader.exec_module(plan_module)


ACL_PAGE = '''
<pre>@inproceedings{suarez-etal-2012-building,
  title = "Building a Multimodal Laughter Database for Emotion Recognition",
  author = "Suarez, Merlin Teodosia  and\n      Cu, Jocelynn  and\n      Maria, Madelene Sta.",
  booktitle = "Proceedings of the Eighth International Conference on Language Resources and Evaluation ({LREC}'12)",
  year = "2012",
  url = "https://aclanthology.org/L12-1459/",
  pages = "2347--2350",
}</pre>
<div class="card-body acl-abstract"><h5>Abstract</h5><span>Laughter is significant.</span></div>
'''


def item(key: str = "IXVEHJSV"):
    return {
        "key": key,
        "data": {
            "key": key,
            "itemType": "conferencePaper",
            "title": "ACTER: A Comparable Corpus for Term Extraction",
            "url": "https://aclanthology.org/L12-1459/",
            "tags": [
                {"tag": "status:abstract-unavailable"},
                {"tag": "status:metadata-conflict"},
                {"tag": "status:needs-review"},
                {"tag": "status:needs-pdf"},
                {"tag": "topic:nlp"},
            ],
        },
    }


def identity_entry(key: str = "IXVEHJSV"):
    return {
        "key": key,
        "status": "conflict",
        "source": "ACL Anthology",
        "sourceTitle": "Building a Multimodal Laughter Database for Emotion Recognition",
        "evidence": {"url": "https://aclanthology.org/L12-1459/", "aclId": "L12-1459"},
    }


class SourceIdentityPlanTests(unittest.TestCase):
    @patch.object(plan_module, "request_text")
    def test_builds_acl_source_identity_plan(self, request_text) -> None:
        request_text.return_value = ACL_PAGE
        edits, report = plan_module.build_source_identity_plan(
            [item()], [identity_entry()], timeout=1
        )
        self.assertEqual("planned", report[0]["status"])
        self.assertEqual("IXVEHJSV", edits[0]["key"])
        self.assertEqual(
            "Building a Multimodal Laughter Database for Emotion Recognition",
            edits[0]["set"]["title"],
        )
        self.assertEqual("2347-2350", edits[0]["set"]["pages"])
        self.assertEqual("Laughter is significant.", edits[0]["set"]["abstractNote"])
        self.assertEqual(
            [
                {"creatorType": "author", "firstName": "Merlin Teodosia", "lastName": "Suarez"},
                {"creatorType": "author", "firstName": "Jocelynn", "lastName": "Cu"},
                {"creatorType": "author", "firstName": "Madelene Sta.", "lastName": "Maria"},
            ],
            edits[0]["setCreators"],
        )
        self.assertEqual(
            ["status:abstract-unavailable", "status:metadata-conflict", "status:needs-review"],
            edits[0]["removeTags"],
        )

    @patch.object(plan_module, "request_text")
    def test_rejects_changed_source_title(self, request_text) -> None:
        request_text.return_value = ACL_PAGE
        entry = identity_entry()
        entry["sourceTitle"] = "Different Source Title"
        edits, report = plan_module.build_source_identity_plan([item()], [entry], timeout=1)
        self.assertEqual([], edits)
        self.assertEqual("rejected", report[0]["status"])

    def test_skips_unsupported_sources(self) -> None:
        entry = identity_entry()
        entry["source"] = "Crossref URL"
        edits, report = plan_module.build_source_identity_plan([item()], [entry], timeout=1)
        self.assertEqual([], edits)
        self.assertEqual("skipped", report[0]["status"])


if __name__ == "__main__":
    unittest.main()
