#!/usr/bin/env python3
"""Build guarded JSONL repair candidates from authoritative source identities."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .metadata_enricher import ACL_ABSTRACT, clean_abstract, request_text, titles_match


CHILD_TYPES = {"annotation", "attachment", "note"}
REVIEW_TAGS = [
    "status:abstract-unavailable",
    "status:metadata-conflict",
    "status:needs-review",
]


class SourcePlanError(ValueError):
    pass


@dataclass(frozen=True)
class SourceMetadata:
    title: str
    creators: list[dict[str, str]]
    year: str
    url: str
    proceedings_title: str
    pages: str
    abstract: str


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourcePlanError(f"cannot read {path}: {exc}") from exc


def load_library(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise SourcePlanError("library input must be a JSON item array")
    return items


def load_identity_report(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    report = payload.get("report") if isinstance(payload, dict) else payload
    if not isinstance(report, list) or any(not isinstance(entry, dict) for entry in report):
        raise SourcePlanError("identity report must contain a report array")
    return report


def item_data(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data")
    return data if isinstance(data, dict) else item


def item_key(item: dict[str, Any]) -> str:
    data = item_data(item)
    return str(item.get("key") or data.get("key") or "")


def strip_bibtex_markup(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\\n", " ")
    value = re.sub(r"\\[a-zA-Z]+\\{([^{}]*)\\}", r"\1", value)
    value = value.replace("{", "").replace("}", "")
    return " ".join(value.split())


def bibtex_block(page: str) -> str:
    text = html.unescape(page)
    start = text.find("@inproceedings")
    if start < 0:
        return ""
    end = text.find("</pre>", start)
    return text[start:end if end > start else len(text)]


def bibtex_field(block: str, field: str) -> str:
    pattern = re.compile(r"\b" + re.escape(field) + r'\s*=\s*"(?P<value>.*?)"\s*,', re.S)
    match = pattern.search(block)
    return strip_bibtex_markup(match.group("value")) if match else ""


def bibtex_creators(block: str) -> list[dict[str, str]]:
    author = bibtex_field(block, "author")
    creators: list[dict[str, str]] = []
    for raw_name in re.split(r"\s+and\s+", author):
        raw_name = " ".join(raw_name.split())
        if not raw_name:
            continue
        if "," in raw_name:
            last, first = (part.strip() for part in raw_name.split(",", 1))
            creators.append({"creatorType": "author", "firstName": first, "lastName": last})
        else:
            creators.append({"creatorType": "author", "name": raw_name})
    return creators


def acl_metadata(url: str, *, timeout: float) -> SourceMetadata:
    page = request_text(url, accept="text/html", timeout=timeout)
    block = bibtex_block(page)
    title = bibtex_field(block, "title")
    creators = bibtex_creators(block)
    year = bibtex_field(block, "year")
    source_url = bibtex_field(block, "url") or url
    proceedings_title = bibtex_field(block, "booktitle")
    pages = bibtex_field(block, "pages").replace("--", "-")
    abstract_match = ACL_ABSTRACT.search(page)
    abstract = clean_abstract(abstract_match.group(1) if abstract_match else "")
    if not title or not creators or not source_url:
        raise SourcePlanError(f"ACL metadata incomplete for {url}")
    return SourceMetadata(
        title=title,
        creators=creators,
        year=year,
        url=source_url,
        proceedings_title=proceedings_title,
        pages=pages,
        abstract=abstract,
    )


def build_source_identity_plan(
    items: list[dict[str, Any]],
    identity_report: list[dict[str, Any]],
    *,
    timeout: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lookup = {
        item_key(item): item_data(item)
        for item in items
        if item_data(item).get("itemType") not in CHILD_TYPES and item_key(item)
    }
    edits: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for entry in identity_report:
        if entry.get("status") != "conflict":
            continue
        key = str(entry.get("key") or "")
        data = lookup.get(key)
        if not data:
            report.append({"key": key, "status": "skipped", "reason": "item not found"})
            continue
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        source = str(entry.get("source") or "")
        url = str(evidence.get("url") or "")
        if source != "ACL Anthology" or not url:
            report.append({"key": key, "status": "skipped", "reason": f"unsupported source {source}"})
            continue
        metadata = acl_metadata(url, timeout=timeout)
        if not titles_match(str(entry.get("sourceTitle") or ""), metadata.title):
            report.append(
                {
                    "key": key,
                    "status": "rejected",
                    "reason": "source title changed since identity audit",
                    "identityAuditTitle": entry.get("sourceTitle"),
                    "fetchedTitle": metadata.title,
                }
            )
            continue
        fields = {
            "title": metadata.title,
            "date": metadata.year,
            "url": metadata.url,
            "proceedingsTitle": metadata.proceedings_title,
            "pages": metadata.pages,
            "abstractNote": metadata.abstract,
        }
        edit: dict[str, Any] = {
            "key": key,
            "set": {name: value for name, value in fields.items() if value},
            "setCreators": metadata.creators,
            "removeTags": [tag for tag in REVIEW_TAGS if tag in {t.get("tag") for t in data.get("tags", []) if isinstance(t, dict)}],
        }
        if data.get("itemType") != "conferencePaper":
            edit["setItemType"] = "conferencePaper"
        edits.append(edit)
        report.append(
            {
                "key": key,
                "status": "planned",
                "source": source,
                "sourceTitle": metadata.title,
                "creators": len(metadata.creators),
                "setFields": sorted(edit["set"]),
                "removeTags": edit["removeTags"],
            }
        )
    return edits, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path, help="JSON from 'zot search ... --all --json'")
    parser.add_argument("identity_report", type=Path, help="JSON from identity_audit.py")
    parser.add_argument("--output", type=Path, help="write JSONL plan here; defaults to stdout")
    parser.add_argument("--report", type=Path, help="write JSON report here")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    try:
        edits, report = build_source_identity_plan(
            load_library(args.library),
            load_identity_report(args.identity_report),
            timeout=args.timeout,
        )
    except SourcePlanError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in edits)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"planned={len(edits)} unresolved={len(report) - len(edits)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
