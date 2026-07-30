from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "zotero-librarian" / "scripts" / "conflict_report.py"
SPEC = importlib.util.spec_from_file_location("conflict_report", SCRIPT)
assert SPEC and SPEC.loader
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


def item(key: str):
    return {
        "key": key,
        "data": {
            "key": key,
            "itemType": "conferencePaper",
            "title": "ACTER: A Comparable Corpus for Term Extraction",
            "date": "2012",
            "url": "https://aclanthology.org/L12-1459/",
            "creators": [
                {"firstName": "Tatiana", "lastName": "Gornostay", "creatorType": "author"},
                {"firstName": "Spela", "lastName": "Vintar", "creatorType": "author"},
            ],
            "tags": [
                {"tag": "status:metadata-conflict"},
                {"tag": "status:needs-review"},
                {"tag": "topic:nlp"},
            ],
        },
    }


def note(parent: str):
    return {
        "key": "NOTE1234",
        "data": {
            "itemType": "note",
            "parentItem": parent,
            "note": "<p>Zotero Librarian metadata conflict audit</p>",
        },
    }


class ConflictReportTests(unittest.TestCase):
    def test_builds_markdown_decision_report(self) -> None:
        identity_report = [
            {
                "key": "IXVEHJSV",
                "status": "conflict",
                "source": "ACL Anthology",
                "zoteroTitle": "ACTER: A Comparable Corpus for Term Extraction",
                "sourceTitle": "Building a Multimodal Laughter Database for Emotion Recognition",
                "evidence": {"aclId": "L12-1459", "url": "https://aclanthology.org/L12-1459/"},
            }
        ]
        text = report.build_report([item("IXVEHJSV"), note("IXVEHJSV")], identity_report)
        self.assertIn("# Metadata Conflict Decision Report", text)
        self.assertIn("- Writes performed: none", text)
        self.assertIn("- Documented conflicts: 1", text)
        self.assertIn("Tatiana Gornostay, Spela Vintar", text)
        self.assertIn("Building a Multimodal Laughter Database for Emotion Recognition", text)
        self.assertIn("Conflict note present: yes", text)
        self.assertIn("Option B", text)

    def test_reports_clean_state(self) -> None:
        text = report.build_report([], [])
        self.assertIn("Conflicts: 0", text)
        self.assertIn("No URL-backed identity conflicts", text)


if __name__ == "__main__":
    unittest.main()
