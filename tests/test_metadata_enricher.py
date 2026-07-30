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
    def test_semantic_scholar_doi_abstract_with_year_check(self, request_text) -> None:
        request_text.return_value = (
            '{"title":"A Sufficiently Specific Example Paper Title",'
            '"year":2024,"abstract":"Authoritative abstract."}'
        )
        result = enricher.fetch_semantic_scholar(
            {
                "doi": "10.1234/example",
                "title": "A Sufficiently Specific Example Paper Title",
                "year": "2024",
            },
            1,
        )
        self.assertEqual("Authoritative abstract.", result.abstract)
        self.assertIn("DOI%3A10.1234%2Fexample", request_text.call_args.args[0])

        request_text.return_value = (
            '{"title":"A Sufficiently Specific Example Paper Title",'
            '"year":2023,"abstract":"Wrong year."}'
        )
        self.assertIsNone(
            enricher.fetch_semantic_scholar(
                {
                    "doi": "10.1234/example",
                    "title": "A Sufficiently Specific Example Paper Title",
                    "year": "2024",
                },
                1,
            )
        )

    @patch.object(enricher, "request_text")
    def test_openalex_reconstructs_abstract_and_checks_year(self, request_text) -> None:
        request_text.return_value = (
            '{"results":[{"display_name":"A Sufficiently Specific Example Paper Title",'
            '"id":"https://openalex.org/W123","doi":"https://doi.org/10.1234/example",'
            '"publication_year":2024,'
            '"locations":[{"landing_page_url":"https://publisher.example/paper",'
            '"pdf_url":"https://publisher.example/paper.pdf"}],'
            '"abstract_inverted_index":'
            '{"Useful":[0],"abstract":[1],"text.":[2]}}]}'
        )
        result = enricher.fetch_openalex(
            {"title": "A Sufficiently Specific Example Paper Title", "year": "2024"}, 1
        )
        self.assertEqual("Useful abstract text.", result.abstract)
        self.assertEqual("https://openalex.org/W123", result.evidence["openalexId"])
        self.assertEqual("10.1234/example", result.evidence["doi"])
        self.assertEqual("title,year", result.evidence["matchBasis"])

    @patch.object(enricher, "request_text")
    def test_openalex_rejects_generic_or_year_mismatched_titles(self, request_text) -> None:
        self.assertIsNone(enricher.fetch_openalex({"title": "Data Intelligence"}, 1))
        request_text.return_value = (
            '{"results":[{"display_name":"A Sufficiently Specific Example Paper Title",'
            '"publication_year":2023,"abstract_inverted_index":{"Wrong":[0]}}]}'
        )
        self.assertIsNone(
            enricher.fetch_openalex(
                {"title": "A Sufficiently Specific Example Paper Title", "year": "2024"}, 1
            )
        )

    @patch.object(enricher, "request_text")
    def test_openalex_rejects_mismatched_acl_identity(self, request_text) -> None:
        request_text.return_value = (
            '{"results":[{"display_name":"BRAT: A Web-Based Tool for NLP-Assisted Text Annotation",'
            '"publication_year":2012,"doi":"https://doi.org/10.1016/wrong",'
            '"locations":[{"landing_page_url":"https://example.org/wrong"}],'
            '"abstract_inverted_index":{"Wrong":[0],"abstract.":[1]}}]}'
        )
        self.assertIsNone(
            enricher.fetch_openalex(
                {
                    "title": "BRAT: A Web-Based Tool for NLP-Assisted Text Annotation",
                    "year": "2012",
                    "url": "https://aclanthology.org/E12-2021/",
                },
                1,
            )
        )

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

    @patch.object(enricher, "request_text")
    def test_official_document_description(self, request_text) -> None:
        request_text.return_value = (
            '<meta property="og:title" content="Example Documentation Page">'
            '<meta name="description" content="This official documentation explains the supported API behavior in detail.">'
        )
        result = enricher.fetch_official_description(
            {"type": "document", "url": "https://docs.example.org/page"}, 1
        )
        self.assertEqual("official page", result.source)

    @patch.object(enricher, "request_text")
    def test_official_description_is_document_only(self, request_text) -> None:
        self.assertIsNone(
            enricher.fetch_official_description(
                {"type": "journalArticle", "url": "https://publisher.example/paper"}, 1
            )
        )
        request_text.assert_not_called()


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

    def test_rejection_report_keeps_candidate_identity_evidence(self) -> None:
        items = [{"key": "ABCD1234", "title": "Expected Paper"}]
        metadata = enricher.Metadata(
            "Different Official Paper",
            "Official abstract.",
            "ACL Anthology",
            {"aclId": "L12-1459", "url": "https://aclanthology.org/L12-1459/"},
        )
        with patch.object(enricher, "PROVIDERS", (lambda item, timeout: metadata,)):
            plan, report = enricher.build_plan(items, timeout=1, delay=0)
        self.assertEqual([], plan)
        self.assertEqual(
            {
                "key": "ABCD1234",
                "status": "rejected",
                "reason": "title mismatch",
                "source": "ACL Anthology",
                "expectedTitle": "Expected Paper",
                "candidateTitle": "Different Official Paper",
                "evidence": {"aclId": "L12-1459", "url": "https://aclanthology.org/L12-1459/"},
            },
            report[0],
        )

    def test_builds_only_deterministic_doi_updates(self) -> None:
        items = [
            {"key": "ABCD1234", "url": "https://doi.org/10.1234/example"},
            {"key": "EFGH5678", "url": "https://arxiv.org/abs/2401.00001v2"},
            {"key": "IJKL9012", "url": "https://example.org/paper"},
        ]
        plan, _ = enricher.build_doi_plan(items)
        self.assertEqual(
            [
                {"key": "ABCD1234", "set": {"DOI": "10.1234/example"}},
                {"key": "EFGH5678", "set": {"DOI": "10.48550/arXiv.2401.00001"}},
            ],
            plan,
        )

    @patch.object(enricher, "request_text")
    def test_crossref_doi_search_requires_exact_title_and_year(self, request_text) -> None:
        request_text.return_value = (
            '{"message":{"items":['
            '{"DOI":"10.1234/right","title":["A Sufficiently Specific Paper Title"],'
            '"published":{"date-parts":[[2024]]}},'
            '{"DOI":"10.1234/wrong-year","title":["A Sufficiently Specific Paper Title"],'
            '"published":{"date-parts":[[2023]]}}]}}'
        )
        doi = enricher.search_crossref_doi(
            {
                "type": "journalArticle",
                "title": "A Sufficiently Specific Paper Title",
                "year": "2024",
            },
            1,
        )
        self.assertEqual("10.1234/right", doi)


if __name__ == "__main__":
    unittest.main()
