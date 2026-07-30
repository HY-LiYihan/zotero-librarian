from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "zotero-librarian" / "scripts" / "librarian_guard.py"
SPEC = importlib.util.spec_from_file_location("librarian_guard", SCRIPT)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


VALID_TAXONOMY = {
    "version": 1,
    "collections": {"inbox": "Inbox"},
    "tags": {
        "allowed_prefixes": ["topic", "status", "priority"],
        "allow_unprefixed": False,
        "exclusive": {
            "status": ["status:to-read", "status:read"],
            "priority": ["priority:low", "priority:high"],
        },
    },
    "policy": {"deletion": "trash-only", "attachment_mode": "stored"},
}


class TaxonomyTests(unittest.TestCase):
    def test_example_taxonomy_is_valid(self) -> None:
        taxonomy = guard.load_toml(ROOT / "taxonomy.example.toml")
        self.assertEqual([], guard.validate_taxonomy(taxonomy))

    def test_installed_skill_taxonomy_is_valid(self) -> None:
        taxonomy = guard.load_toml(
            ROOT / "skills" / "zotero-librarian" / "references" / "taxonomy.example.toml"
        )
        self.assertEqual([], guard.validate_taxonomy(taxonomy))

    def test_rejects_permanent_deletion_policy(self) -> None:
        taxonomy = {**VALID_TAXONOMY, "policy": {"deletion": "erase", "attachment_mode": "stored"}}
        self.assertIn("policy.deletion must be 'trash-only'", guard.validate_taxonomy(taxonomy))


class PlanTests(unittest.TestCase):
    def validate_lines(self, text: str, item_types=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.jsonl"
            path.write_text(text, encoding="utf-8")
            return guard.validate_plan(path, VALID_TAXONOMY, item_types)

    def test_accepts_safe_plan(self) -> None:
        errors, entries, trash_entries = self.validate_lines(
            '{"key":"ABCD1234","addTags":["topic:robotics","status:to-read"],"trash":false}\n'
        )
        self.assertEqual([], errors)
        self.assertEqual(1, entries)
        self.assertEqual(0, trash_entries)

    def test_accepts_top_level_set_creators(self) -> None:
        errors, entries, _ = self.validate_lines(
            '{"key":"ABCD1234","setCreators":['
            '{"creatorType":"author","firstName":"Ada","lastName":"Lovelace"},'
            '{"creatorType":"author","name":"Example Consortium"}],'
            '"removeTags":["status:metadata-conflict"]}\n'
        )
        self.assertEqual([], errors)
        self.assertEqual(1, entries)

    def test_accepts_trash_only(self) -> None:
        errors, _, trash_entries = self.validate_lines('{"key":"ABCD1234","trash":true}\n')
        self.assertEqual([], errors)
        self.assertEqual(1, trash_entries)

    def test_rejects_unknown_and_permanent_delete_fields(self) -> None:
        errors, _, _ = self.validate_lines('{"key":"ABCD1234","eraseTx":true}\n')
        self.assertTrue(any("unsupported fields" in error for error in errors))
        self.assertTrue(any("permanent-delete" in error for error in errors))

    def test_rejects_complex_fields_inside_set(self) -> None:
        errors, _, _ = self.validate_lines(
            '{"key":"ABCD1234","set":{"creators":[{"lastName":"Example"}]}}\n'
        )
        self.assertTrue(any("unsupported set fields: creators" in error for error in errors))


    def test_rejects_fields_invalid_for_known_item_type(self) -> None:
        errors, _, _ = self.validate_lines(
            '{"key":"ABCD1234","set":{"DOI":"10.1234/example","bookTitle":"Proceedings"}}\n',
            {"ABCD1234": "webpage"},
        )
        self.assertTrue(any("fields invalid for itemType 'webpage': bookTitle" in error for error in errors))

    def test_rejects_malformed_set_creators(self) -> None:
        errors, _, _ = self.validate_lines(
            '{"key":"ABCD1234","setCreators":[{"firstName":"Ada"},'
            '{"creatorType":"author","name":"Team","lastName":"Team"}]}\n'
        )
        self.assertTrue(any("creatorType must be a non-empty string" in error for error in errors))
        self.assertTrue(any("lastName must be a non-empty string" in error for error in errors))
        self.assertTrue(any("must not mix name" in error for error in errors))

    def test_rejects_conflicting_exclusive_tags(self) -> None:
        errors, _, _ = self.validate_lines(
            '{"key":"ABCD1234","addTags":["status:to-read","status:read"]}\n'
        )
        self.assertTrue(any("exclusive group" in error for error in errors))

    def test_rejects_unprefixed_tags(self) -> None:
        errors, _, _ = self.validate_lines('{"key":"ABCD1234","addTags":["To Read"]}\n')
        self.assertTrue(any("unprefixed tags are disabled" in error for error in errors))

    def test_allows_removing_legacy_unprefixed_tags(self) -> None:
        errors, _, _ = self.validate_lines(
            '{"key":"ABCD1234","addTags":["status:to-read"],"removeTags":["To Read"]}\n'
        )
        self.assertEqual([], errors)

    def test_rejects_duplicate_item_keys(self) -> None:
        errors, _, _ = self.validate_lines(
            '{"key":"ABCD1234","trash":false}\n{"key":"ABCD1234","trash":true}\n'
        )
        self.assertTrue(any("duplicate item key" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
