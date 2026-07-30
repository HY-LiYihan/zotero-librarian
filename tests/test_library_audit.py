from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "zotero-librarian" / "scripts" / "library_audit.py"
SPEC = importlib.util.spec_from_file_location("library_audit", SCRIPT)
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_module
SPEC.loader.exec_module(audit_module)


def item(
    key: str,
    *,
    item_type: str = "journalArticle",
    tags: tuple[str, ...] = (),
    pdf: bool = False,
    abstract: str = "Abstract",
    date: str = "2024",
    creators: bool = True,
):
    value = {
        "key": key,
        "data": {
            "itemType": item_type,
            "tags": [{"tag": tag} for tag in tags],
            "abstractNote": abstract,
            "date": date,
            "creators": [{"lastName": "Example"}] if creators else [],
        },
        "links": {},
    }
    if pdf:
        value["links"]["attachment"] = {"attachmentType": "application/pdf"}
    return value


def note(key: str, parent: str, body: str):
    return {
        "key": key,
        "data": {
            "itemType": "note",
            "parentItem": parent,
            "note": body,
        },
    }


class AuditTests(unittest.TestCase):
    def test_excludes_children_and_reports_clean_parent(self) -> None:
        values = [
            item("ABCD1234", tags=("topic:test",), pdf=True),
            item("EFGH5678", item_type="attachment", tags=()),
        ]
        result = audit_module.audit(values)
        self.assertEqual(1, result["parents"])
        self.assertEqual(1, result["withPdf"])
        self.assertTrue(all(count == 0 for count in result["counts"].values()))

    def test_distinguishes_pdf_queue_and_abstract_applicability(self) -> None:
        values = [
            item(
                "ABCD1234",
                tags=("topic:test", "status:needs-pdf", "status:abstract-not-applicable"),
                abstract="",
            ),
            item("EFGH5678", tags=("topic:test",), pdf=True, abstract=""),
            item("IJKL9012", tags=("topic:test", "status:needs-pdf"), pdf=True),
        ]
        result = audit_module.audit(values)
        self.assertEqual(["EFGH5678"], result["findings"]["actionableMissingAbstract"])
        self.assertEqual(["IJKL9012"], result["findings"]["staleNeedsPdf"])
        self.assertEqual([], result["findings"]["unqueuedMissingPdf"])

    def test_tracks_verified_unavailable_abstract_without_hiding_metadata_conflict(self) -> None:
        values = [
            item(
                "ABCD1234",
                tags=("topic:test", "status:needs-pdf", "status:abstract-unavailable"),
                abstract="",
            ),
            item(
                "EFGH5678",
                tags=(
                    "topic:test",
                    "status:needs-pdf",
                    "status:abstract-unavailable",
                    "status:metadata-conflict",
                ),
                abstract="",
            ),
        ]
        result = audit_module.audit(values)
        self.assertEqual([], result["findings"]["actionableMissingAbstract"])
        self.assertEqual(["ABCD1234", "EFGH5678"], result["findings"]["abstractUnavailable"])
        self.assertEqual(["EFGH5678"], result["findings"]["metadataConflict"])
        self.assertEqual(["EFGH5678"], result["findings"]["metadataConflictUndocumented"])

    def test_distinguishes_documented_metadata_conflicts(self) -> None:
        values = [
            item("ABCD1234", tags=("topic:test", "status:metadata-conflict")),
            item("EFGH5678", tags=("topic:test", "status:metadata-conflict")),
            note(
                "NOTE1234",
                "ABCD1234",
                "<p>Zotero Librarian metadata conflict audit: current URL mismatch.</p>",
            ),
        ]
        result = audit_module.audit(values)
        self.assertEqual(["ABCD1234", "EFGH5678"], result["findings"]["metadataConflict"])
        self.assertEqual(["ABCD1234"], result["findings"]["metadataConflictDocumented"])
        self.assertEqual(["EFGH5678"], result["findings"]["metadataConflictUndocumented"])

    def test_reports_missing_topic_and_unqueued_pdf(self) -> None:
        result = audit_module.audit([item("ABCD1234", tags=("priority:high",))])
        self.assertEqual(["ABCD1234"], result["findings"]["withoutTopic"])
        self.assertEqual(["ABCD1234"], result["findings"]["unqueuedMissingPdf"])

    def test_respects_date_and_creator_applicability_tags(self) -> None:
        value = item(
            "ABCD1234",
            tags=(
                "topic:test",
                "status:needs-pdf",
                "status:date-not-applicable",
                "status:creator-not-applicable",
            ),
            date="",
            creators=False,
        )
        result = audit_module.audit([value])
        self.assertEqual([], result["findings"]["missingDate"])
        self.assertEqual([], result["findings"]["missingCreators"])


if __name__ == "__main__":
    unittest.main()
