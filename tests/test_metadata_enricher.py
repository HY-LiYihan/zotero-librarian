from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "zotero-librarian" / "scripts" / "metadata_enricher.py"
SPEC = importlib.util.spec_from_file_location("metadata_enricher", SCRIPT)
assert SPEC and SPEC.loader
enricher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = enricher
SPEC.loader.exec_module(enricher)


class MatchingTests(unittest.TestCase):
    def test_normalizes_punctuation_and_case(self) -> None:
        self.assertTrue(enricher.titles_match("ReAct: Reasoning & Acting", "ReAct — Reasoning and Acting"))

    def test_rejects_different_titles(self) -> None:
        self.assertFalse(enricher.titles_match("A short title", "A different paper"))


class ProviderTests(unittest.TestCase):
    @patch.object(enricher, "request_text")
    def test_arxiv_atom(self, request_text) -> None:
        request_text.return_value = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Example Paper</title><summary>  An abstract. </summary>
        </entry></feed>"""
        result = enricher.fetch_arxiv(
            {"url": "https://arxiv.org/abs/2401.00001", "doi": ""}, 1
        )
        self.assertEqual("An abstract.", result.abstract)

    @patch.object(enricher, "request_text")
    def test_crossref_jats_abstract(self, request_text) -> None:
        request_text.return_value = (
            '{"message":{"title":["Example Paper"],'
            '"abstract":"<jats:p>Useful result.</jats:p>"}}'
        )
        result = enricher.fetch_crossref({"doi": "10.1234/example"}, 1)
        self.assertEqual("Useful result.", result.abstract)

    @patch.object(enricher, "request_text")
    def test_crossref_extracts_doi_from_publisher_url(self, request_text) -> None:
        request_text.return_value = (
            '{"message":{"title":["Example Paper"],"abstract":"Useful result."}}'
        )
        result = enricher.fetch_crossref(
            {"url": "https://publisher.example/doi/10.1234/example"}, 1
        )
        self.assertEqual("Useful result.", result.abstract)
        self.assertIn("10.1234%2Fexample", request_text.call_args.args[0])

    @patch.object(enricher, "request_text")
    def test_acl_meta(self, request_text) -> None:
        request_text.return_value = (
            '<meta name="citation_title" content="Example Paper">'
            '<meta property="og:description" content="Author. Venue. 2024.">'
            '<div class="card-body acl-abstract"><h5>Abstract</h5>'
            '<span>Official abstract.</span></div>'
        )
        result = enricher.fetch_html_meta({"url": "https://aclanthology.org/2024.test-1/"}, 1)
        self.assertEqual("Official abstract.", result.abstract)

    @patch.object(enricher, "request_text")
    def test_acl_does_not_treat_citation_description_as_abstract(self, request_text) -> None:
        request_text.return_value = (
            '<meta name="citation_title" content="Example Paper">'
            '<meta property="og:description" content="Author. Venue. 2024.">'
        )
        self.assertIsNone(
            enricher.fetch_html_meta({"url": "https://aclanthology.org/2024.test-1/"}, 1)
        )


class PlanTests(unittest.TestCase):
    def test_fills_only_empty_abstracts_and_rejects_mismatch(self) -> None:
        items = [
            {"key": "ABCD1234", "title": "Example Paper", "url": "https://arxiv.org/abs/1"},
            {"key": "EFGH5678", "title": "Existing", "abstractNote": "Keep me"},
            {"key": "IJKL9012", "title": "Wrong Paper", "url": "https://arxiv.org/abs/2"},
        ]
        metadata = enricher.Metadata("Example Paper", "Official abstract.", "arXiv")
        with patch.object(enricher, "PROVIDERS", (lambda item, timeout: metadata,)):
            plan, report = enricher.build_plan(items, timeout=1, delay=0)
        self.assertEqual([{"key": "ABCD1234", "set": {"abstractNote": "Official abstract."}}], plan)
        self.assertEqual(["planned", "skipped", "rejected"], [entry["status"] for entry in report])


if __name__ == "__main__":
    unittest.main()
