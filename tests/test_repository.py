from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def tracked_resource_files(self, root: Path) -> list[Path]:
        return sorted(
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )

    def test_no_generated_or_secret_files(self) -> None:
        forbidden_names = {".DS_Store", "private.env", ".env", "zotero.sqlite"}
        found = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.name in forbidden_names]
        self.assertEqual([], found)

    def test_no_zotero_api_key_literals(self) -> None:
        pattern = re.compile(r"ZOTERO_API_KEY\s*=")
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix in {".pyc"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if pattern.search(text):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)


    def test_readmes_document_completion_gates(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        for value in (english, chinese):
            self.assertIn("goal_status.py", value)
            self.assertIn("automationComplete", value)
            self.assertIn("fullComplete", value)
            self.assertIn("source_identity_plan.py", value)

    def test_beginner_docs_cover_forward_test_feedback(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        setup = (ROOT / "skills" / "zotero-librarian" / "references" / "setup.md").read_text(encoding="utf-8")
        self.assertIn("First-time smoke test expectation", english)
        self.assertIn("小白 smoke test", chinese)
        self.assertIn("install-codex-skill", english)
        self.assertIn("zotero-librarian --json doctor --offline", english)
        self.assertIn("zotero-librarian --json doctor --offline", chinese)
        self.assertIn("Python 3.9/3.10", english)
        self.assertIn("## Live Setup Order", setup)
        self.assertIn("1. Install `zotero-agent`.", setup)
        self.assertIn("2. Install the matching bridge XPI", setup)
        self.assertIn("Do not use a Zotero Web API key", setup)

    def test_skill_has_no_personal_paths_or_taxonomy(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "skills" / "zotero-librarian").rglob("*")
            if path.is_file() and path.suffix in {".md", ".py", ".yaml"}
        )
        for forbidden in ("/Users/", "18040906", "RLToken", "Robot Learning"):
            self.assertNotIn(forbidden, text)

    def test_embedded_skill_matches_canonical_skill(self) -> None:
        canonical = ROOT / "skills" / "zotero-librarian"
        embedded = ROOT / "src" / "zotero_librarian" / "resources" / "skills" / "zotero-librarian"
        canonical_files = self.tracked_resource_files(canonical)
        embedded_files = self.tracked_resource_files(embedded)
        self.assertEqual(canonical_files, embedded_files)
        for relative in canonical_files:
            self.assertEqual(
                (canonical / relative).read_text(encoding="utf-8"),
                (embedded / relative).read_text(encoding="utf-8"),
                str(relative),
            )


if __name__ == "__main__":
    unittest.main()
