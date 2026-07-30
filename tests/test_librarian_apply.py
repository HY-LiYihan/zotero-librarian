from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "zotero-librarian" / "scripts" / "librarian_apply.py"
SPEC = importlib.util.spec_from_file_location("librarian_apply", SCRIPT)
assert SPEC and SPEC.loader
apply_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply_module)


class ExtendedApplyTests(unittest.TestCase):
    def test_loads_and_summarizes_creator_plan_without_zotero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.jsonl"
            path.write_text(
                '{"key":"ABCD1234","setCreators":['
                '{"creatorType":"author","firstName":"Ada","lastName":"Lovelace"}],'
                '"removeTags":["status:metadata-conflict"]}\n',
                encoding="utf-8",
            )
            edits = apply_module.load_edits(path)
        self.assertEqual([], apply_module.validate_edits(edits))
        self.assertEqual(
            {
                "ok": True,
                "dryRun": True,
                "edits": 1,
                "keys": ["ABCD1234"],
                "operations": [
                    {
                        "key": "ABCD1234",
                        "setItemType": None,
                        "set": [],
                        "setCreators": 1,
                        "addTags": [],
                        "removeTags": ["status:metadata-conflict"],
                    }
                ],
            },
            apply_module.dry_run_summary(edits),
        )


    def test_accepts_item_type_and_field_repairs(self) -> None:
        edits = [
            {
                "key": "ABCD1234",
                "setItemType": "bookSection",
                "set": {"DOI": "10.1234/example", "bookTitle": "Proceedings"},
                "removeTags": ["status:needs-review"],
            }
        ]
        self.assertEqual([], apply_module.validate_edits(edits))
        summary = apply_module.dry_run_summary(edits)
        self.assertEqual("bookSection", summary["operations"][0]["setItemType"])
        self.assertEqual(["DOI", "bookTitle"], summary["operations"][0]["set"])

    def test_rejects_unsupported_set_and_item_type_fields(self) -> None:
        errors = apply_module.validate_edits(
            [{"key": "ABCD1234", "setItemType": "notAType", "set": {"creators": []}}]
        )
        self.assertTrue(any("setItemType must be one of" in error for error in errors))
        self.assertTrue(any("unsupported set fields: creators" in error for error in errors))

    def test_rejects_upstream_apply_fields(self) -> None:
        errors = apply_module.validate_edits(
            [{"key": "ABCD1234", "set": {"title": "Nope"}, "trash": True}]
        )
        self.assertTrue(any("unsupported fields" in error for error in errors))

    def test_rejects_malformed_creator_entries(self) -> None:
        errors = apply_module.validate_edits(
            [
                {
                    "key": "ABCD1234",
                    "setCreators": [
                        {"creatorType": "author", "firstName": "Ada"},
                        {"creatorType": "author", "name": "Team", "lastName": "Team"},
                    ],
                }
            ]
        )
        self.assertTrue(any("lastName must be a non-empty string" in error for error in errors))
        self.assertTrue(any("must not mix name" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
