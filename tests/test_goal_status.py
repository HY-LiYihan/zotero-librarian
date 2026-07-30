from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "zotero-librarian" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "goal_status.py"
SPEC = importlib.util.spec_from_file_location("goal_status", SCRIPT)
assert SPEC and SPEC.loader
status_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = status_module
SPEC.loader.exec_module(status_module)


def item(key: str, tags: tuple[str, ...] = ("topic:test", "status:needs-pdf")):
    return {
        "key": key,
        "data": {
            "key": key,
            "itemType": "conferencePaper",
            "title": "Example",
            "abstractNote": "Abstract",
            "date": "2024",
            "creators": [{"lastName": "Example"}],
            "tags": [{"tag": tag} for tag in tags],
        },
        "links": {},
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


class GoalStatusTests(unittest.TestCase):
    def test_separates_automation_complete_from_full_complete(self) -> None:
        values = [
            item(
                "ABCD1234",
                tags=(
                    "topic:test",
                    "status:needs-pdf",
                    "status:metadata-conflict",
                    "status:needs-review",
                ),
            ),
            note("ABCD1234"),
        ]
        result = status_module.build_status(values, expected_items=1)
        self.assertTrue(result["parentCountOk"])
        self.assertTrue(result["automationComplete"])
        self.assertFalse(result["fullComplete"])
        self.assertEqual(["ABCD1234"], result["manualDecisionItems"])
        self.assertIn("No Zotero write is safe", " ".join(result["nextActions"]))

    def test_reports_full_completion(self) -> None:
        result = status_module.build_status([item("ABCD1234")], expected_items=1)
        self.assertTrue(result["automationComplete"])
        self.assertTrue(result["fullComplete"])
        self.assertEqual([], result["manualDecisionItems"])

    def test_parent_count_mismatch_blocks_both_gates(self) -> None:
        result = status_module.build_status([item("ABCD1234")], expected_items=2)
        self.assertFalse(result["parentCountOk"])
        self.assertFalse(result["automationComplete"])
        self.assertFalse(result["fullComplete"])
        self.assertEqual(["expected 2 parent items, found 1"], result["automationErrors"])


if __name__ == "__main__":
    unittest.main()
