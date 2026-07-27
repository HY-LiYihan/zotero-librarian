#!/usr/bin/env python3
"""Audit Zotero parent-item completeness from a full local JSON search export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CHILD_TYPES = {"annotation", "attachment", "note"}
SCHOLARLY_TYPES = {"bookSection", "conferencePaper", "journalArticle", "preprint", "report"}


class AuditError(ValueError):
    pass


def load_items(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read input JSON: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise AuditError("input must be the JSON array from 'zot search ... --all --json'")
    return value


def item_tags(item: dict[str, Any]) -> set[str]:
    tags = item.get("data", {}).get("tags", [])
    return {
        str(tag.get("tag"))
        for tag in tags
        if isinstance(tag, dict) and isinstance(tag.get("tag"), str)
    }


def has_pdf(item: dict[str, Any]) -> bool:
    return item.get("links", {}).get("attachment", {}).get("attachmentType") == "application/pdf"


def audit(items: list[dict[str, Any]]) -> dict[str, Any]:
    parents = [
        item
        for item in items
        if item.get("data", {}).get("itemType") not in CHILD_TYPES
    ]
    findings: dict[str, list[str]] = {
        "noTags": [],
        "withoutTopic": [],
        "staleNeedsPdf": [],
        "unqueuedMissingPdf": [],
        "actionableMissingAbstract": [],
        "missingDate": [],
        "missingCreators": [],
    }
    with_pdf = 0
    for item in parents:
        data = item.get("data", {})
        key = str(item.get("key") or data.get("key") or "")
        tags = item_tags(item)
        pdf = has_pdf(item)
        with_pdf += int(pdf)
        if not tags:
            findings["noTags"].append(key)
        if not any(tag.startswith("topic:") for tag in tags):
            findings["withoutTopic"].append(key)
        if pdf and "status:needs-pdf" in tags:
            findings["staleNeedsPdf"].append(key)
        if (
            not pdf
            and data.get("itemType") in SCHOLARLY_TYPES
            and "status:needs-pdf" not in tags
        ):
            findings["unqueuedMissingPdf"].append(key)
        if not str(data.get("abstractNote") or "").strip() and not (
            "status:abstract-not-applicable" in tags
        ):
            findings["actionableMissingAbstract"].append(key)
        if not str(data.get("date") or "").strip():
            findings["missingDate"].append(key)
        if not data.get("creators"):
            findings["missingCreators"].append(key)

    return {
        "parents": len(parents),
        "withPdf": with_pdf,
        "withoutPdf": len(parents) - with_pdf,
        "topicCoverage": len(parents) - len(findings["withoutTopic"]),
        "findings": findings,
        "counts": {name: len(keys) for name, keys in findings.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--expect-items", type=int, help="fail if the parent-item count changes")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on tag/PDF queue inconsistencies or actionable missing abstracts",
    )
    args = parser.parse_args()
    try:
        result = audit(load_items(args.input))
    except AuditError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
        return 2
    errors: list[str] = []
    if args.expect_items is not None and result["parents"] != args.expect_items:
        errors.append(f"expected {args.expect_items} parent items, found {result['parents']}")
    if args.strict:
        for field in ("noTags", "withoutTopic", "staleNeedsPdf", "unqueuedMissingPdf", "actionableMissingAbstract"):
            if result["counts"][field]:
                errors.append(f"{field}: {result['counts'][field]}")
    print(json.dumps({"ok": not errors, **result, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
