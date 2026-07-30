from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "zotero-librarian" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "decision_packet.py"
SPEC = importlib.util.spec_from_file_location("decision_packet", SCRIPT)
assert SPEC and SPEC.loader
packet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = packet
SPEC.loader.exec_module(packet)


def item(key: str = "IXVEHJSV"):
    return {
        "key": key,
        "data": {
            "key": key,
            "itemType": "conferencePaper",
            "title": "ACTER: A Comparable Corpus for Term Extraction",
            "abstractNote": "Abstract",
            "date": "2012",
            "url": "https://aclanthology.org/L12-1459/",
            "creators": [
                {"firstName": "Tatiana", "lastName": "Gornostay", "creatorType": "author"},
                {"firstName": "Spela", "lastName": "Vintar", "creatorType": "author"},
            ],
            "tags": [
                {"tag": "topic:nlp"},
                {"tag": "status:needs-pdf"},
                {"tag": "status:metadata-conflict"},
                {"tag": "status:needs-review"},
            ],
        },
        "links": {},
    }


def note(parent: str = "IXVEHJSV"):
    return {
        "key": "NOTE1234",
        "data": {
            "itemType": "note",
            "parentItem": parent,
            "note": "<p>Zotero Librarian metadata conflict audit</p>",
        },
    }


def identity_entry(key: str = "IXVEHJSV"):
    return {
        "key": key,
        "status": "conflict",
        "source": "ACL Anthology",
        "zoteroTitle": "ACTER: A Comparable Corpus for Term Extraction",
        "sourceTitle": "Building a Multimodal Laughter Database for Emotion Recognition",
        "evidence": {"aclId": "L12-1459", "url": "https://aclanthology.org/L12-1459/"},
    }


class DecisionPacketTests(unittest.TestCase):
    def test_builds_user_choice_packet(self) -> None:
        text = packet.build_packet(
            [item(), note()],
            [identity_entry()],
            expected_items=1,
            source_plan_report=[
                {
                    "key": "IXVEHJSV",
                    "status": "planned",
                    "setFields": ["title", "abstractNote"],
                    "creators": 3,
                    "removeTags": ["status:metadata-conflict", "status:needs-review"],
                }
            ],
        )
        self.assertIn("# Zotero Identity Decision Packet", text)
        self.assertIn("Writes performed: none", text)
        self.assertIn("Automation complete: true", text)
        self.assertIn("Full complete: false", text)
        self.assertIn("- A: Keep the current Zotero title identity", text)
        self.assertIn("- B: Adopt the source identity", text)
        self.assertIn("- C: Leave this item in manual review", text)
        self.assertIn("Set fields: title, abstractNote", text)
        self.assertIn("Reply with one of: A, B, or C", text)

    def test_reports_no_decision_needed(self) -> None:
        clean = item("ABCD1234")
        clean["data"]["tags"] = [{"tag": "topic:nlp"}, {"tag": "status:needs-pdf"}]
        text = packet.build_packet([clean], [], expected_items=1)
        self.assertIn("Full complete: true", text)
        self.assertIn("No identity conflicts require a user decision", text)


if __name__ == "__main__":
    unittest.main()
