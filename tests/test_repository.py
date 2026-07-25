from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
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

    def test_skill_has_no_personal_paths_or_taxonomy(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "skills" / "zotero-librarian").rglob("*")
            if path.is_file() and path.suffix in {".md", ".py", ".yaml"}
        )
        for forbidden in ("/Users/", "18040906", "RLToken", "Robot Learning"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
