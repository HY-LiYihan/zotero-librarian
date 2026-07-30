from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "zotero-librarian" / "scripts"
SCRIPT = SCRIPT_DIR / "identity_audit.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("identity_audit", SCRIPT)
assert SPEC and SPEC.loader
identity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = identity
SPEC.loader.exec_module(identity)


def item(key: str, title: str, **data):
    return {"key": key, "data": {"key": key, "itemType": "conferencePaper", "title": title, **data}}


class ProviderTests(unittest.TestCase):
    @patch.object(identity, "request_text")
    def test_reads_acl_title_without_requiring_abstract(self, request_text) -> None:
        request_text.return_value = '<meta name="citation_title" content="Official ACL Paper">'
        record = identity.fetch_html_record({"url": "https://aclanthology.org/L12-1459/"}, 1)
        self.assertEqual("Official ACL Paper", record.title)
        self.assertEqual("ACL Anthology", record.source)
        self.assertEqual("L12-1459", record.evidence["aclId"])

    @patch.object(identity, "request_text")
    def test_reads_crossref_title_from_doi_url(self, request_text) -> None:
        request_text.return_value = '{"message":{"title":["Official DOI Paper"]}}'
        record = identity.fetch_crossref_url_record({"url": "https://doi.org/10.1234/example"}, 1)
        self.assertEqual("Official DOI Paper", record.title)
        self.assertEqual("Crossref URL", record.source)
        self.assertIn("10.1234%2Fexample", request_text.call_args.args[0])

    @patch.object(identity, "request_text")
    def test_crossref_title_strips_jats_markup(self, request_text) -> None:
        request_text.return_value = (
            '{"message":{"title":["Academic <scp>L2</scp> Writing and Word <i>N</i> -Grams"]}}'
        )
        report = identity.audit_identity(
            [
                item(
                    "ABCD1234",
                    "Academic L2 Writing and Word N-Grams",
                    url="https://doi.org/10.1234/example",
                )
            ],
            timeout=1,
            delay=0,
        )
        self.assertEqual("match", report[0]["status"])

    @patch.object(identity, "request_text")
    def test_reads_crossref_title_from_doi_field_only_when_requested(self, request_text) -> None:
        request_text.return_value = '{"message":{"title":["Official DOI Paper"]}}'
        default_report = identity.audit_identity(
            [item("ABCD1234", "Official DOI Paper", DOI="10.1234/example")],
            timeout=1,
            delay=0,
        )
        self.assertEqual("unresolved", default_report[0]["status"])
        request_text.assert_not_called()

        doi_report = identity.audit_identity(
            [item("ABCD1234", "Official DOI Paper", DOI="10.1234/example")],
            timeout=1,
            delay=0,
            include_doi_field=True,
        )
        self.assertEqual("match", doi_report[0]["status"])
        self.assertEqual("Crossref DOI field", doi_report[0]["source"])

    @patch.object(identity, "request_text")
    def test_reads_arxiv_title_from_atom(self, request_text) -> None:
        request_text.return_value = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title> Official arXiv Paper </title>
        </entry></feed>"""
        record = identity.fetch_arxiv_record({"url": "https://arxiv.org/abs/2401.00001"}, 1)
        self.assertEqual("Official arXiv Paper", record.title)


class AuditTests(unittest.TestCase):
    def test_reports_conflict_when_supported_url_title_disagrees(self) -> None:
        record = identity.IdentityRecord(
            "Building a Multimodal Laughter Database for Emotion Recognition",
            "ACL Anthology",
            {"aclId": "L12-1459"},
        )
        with patch.object(identity, "URL_PROVIDERS", (lambda data, timeout: record,)):
            report = identity.audit_identity(
                [item("IXVEHJSV", "ACTER: A Comparable Corpus for Term Extraction")],
                timeout=1,
                delay=0,
            )
        self.assertEqual("conflict", report[0]["status"])
        self.assertEqual("ACL Anthology", report[0]["source"])
        self.assertEqual("L12-1459", report[0]["evidence"]["aclId"])

    def test_reports_match_for_equivalent_titles(self) -> None:
        record = identity.IdentityRecord("ReAct — Reasoning and Acting", "arXiv", {"arxivId": "1"})
        with patch.object(identity, "URL_PROVIDERS", (lambda data, timeout: record,)):
            report = identity.audit_identity(
                [item("ABCD1234", "ReAct: Reasoning & Acting")],
                timeout=1,
                delay=0,
            )
        self.assertEqual("match", report[0]["status"])


    def test_filters_to_requested_keys(self) -> None:
        record = identity.IdentityRecord("Official Paper", "ACL Anthology")
        with patch.object(identity, "URL_PROVIDERS", (lambda data, timeout: record,)):
            report = identity.audit_identity(
                [
                    item("ABCD1234", "Official Paper"),
                    item("EFGH5678", "Official Paper"),
                ],
                timeout=1,
                delay=0,
                keys={"EFGH5678"},
            )
        self.assertEqual(["EFGH5678"], [entry["key"] for entry in report])

    def test_network_errors_are_reported_without_crashing(self) -> None:
        def provider(data, timeout):
            raise OSError("network timeout")

        with patch.object(identity, "URL_PROVIDERS", (provider,)):
            report = identity.audit_identity(
                [item("ABCD1234", "First Paper")],
                timeout=1,
                delay=0,
                workers=2,
            )
        self.assertEqual("unresolved", report[0]["status"])
        self.assertIn("network timeout", report[0]["reason"])

    def test_parallel_workers_preserve_input_order(self) -> None:
        def provider(data, timeout):
            return identity.IdentityRecord(str(data["title"]), "test")

        with patch.object(identity, "URL_PROVIDERS", (provider,)):
            report = identity.audit_identity(
                [
                    item("ABCD1234", "First Paper"),
                    item("EFGH5678", "Second Paper"),
                ],
                timeout=1,
                delay=0,
                workers=2,
            )
        self.assertEqual(["ABCD1234", "EFGH5678"], [entry["key"] for entry in report])

    def test_skips_child_items_and_reports_unresolved_parents(self) -> None:
        values = [
            {"key": "NOTE1234", "data": {"itemType": "note", "title": "Child"}},
            item("ABCD1234", "Unsupported Page", url="https://example.org/page"),
        ]
        report = identity.audit_identity(values, timeout=1, delay=0)
        self.assertEqual(1, len(report))
        self.assertEqual("unresolved", report[0]["status"])


if __name__ == "__main__":
    unittest.main()
