#!/usr/bin/env python3
"""Create a Markdown decision report for documented metadata conflicts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CHILD_TYPES = {"annotation", "attachment", "note"}
CONFLICT_NOTE_MARKER = "Zotero Librarian metadata conflict audit"


class ConflictReportError(ValueError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConflictReportError(f"cannot read {path}: {exc}") from exc


def load_library(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ConflictReportError("library input must be a JSON item array")
    return items


def load_identity_report(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    report = payload.get("report") if isinstance(payload, dict) else payload
    if not isinstance(report, list) or any(not isinstance(entry, dict) for entry in report):
        raise ConflictReportError("identity report must contain a report array")
    return report


def item_data(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data")
    return data if isinstance(data, dict) else item


def item_key(item: dict[str, Any]) -> str:
    data = item_data(item)
    return str(item.get("key") or data.get("key") or "")


def creators_text(data: dict[str, Any]) -> str:
    values: list[str] = []
    for creator in data.get("creators") or []:
        if not isinstance(creator, dict):
            continue
        name = " ".join(
            part
            for part in (
                str(creator.get("firstName") or "").strip(),
                str(creator.get("lastName") or "").strip(),
            )
            if part
        )
        if not name:
            name = str(creator.get("name") or "").strip()
        if name:
            values.append(name)
    return ", ".join(values) if values else "(none)"


def tags_text(data: dict[str, Any]) -> str:
    tags = sorted(
        str(tag.get("tag"))
        for tag in data.get("tags") or []
        if isinstance(tag, dict) and isinstance(tag.get("tag"), str)
    )
    return ", ".join(tags) if tags else "(none)"


def conflict_note_parents(items: list[dict[str, Any]]) -> set[str]:
    parents: set[str] = set()
    for item in items:
        data = item_data(item)
        if data.get("itemType") != "note":
            continue
        parent = data.get("parentItem")
        note = str(data.get("note") or "")
        if isinstance(parent, str) and CONFLICT_NOTE_MARKER in note:
            parents.add(parent)
    return parents


def evidence_text(entry: dict[str, Any]) -> str:
    evidence = entry.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        return "(none)"
    return ", ".join(f"{key}={value}" for key, value in sorted(evidence.items()))


def build_report(items: list[dict[str, Any]], identity_report: list[dict[str, Any]]) -> str:
    lookup = {
        item_key(item): item_data(item)
        for item in items
        if item_data(item).get("itemType") not in CHILD_TYPES and item_key(item)
    }
    documented = conflict_note_parents(items)
    conflicts = [entry for entry in identity_report if entry.get("status") == "conflict"]
    lines = [
        "# Metadata Conflict Decision Report",
        "",
        f"- Conflicts: {len(conflicts)}",
        f"- Documented conflicts: {sum(1 for entry in conflicts if entry.get('key') in documented)}",
        "- Writes performed: none",
        "",
    ]
    if not conflicts:
        lines.extend(["No URL-backed identity conflicts were reported.", ""])
        return "\n".join(lines)

    for entry in conflicts:
        key = str(entry.get("key") or "")
        data = lookup.get(key, {})
        lines.extend(
            [
                f"## {key}",
                "",
                "### Current Zotero Identity",
                "",
                f"- Item type: {data.get('itemType') or '(unknown)'}",
                f"- Title: {data.get('title') or entry.get('zoteroTitle') or '(missing)'}",
                f"- Creators: {creators_text(data)}",
                f"- Date: {data.get('date') or '(missing)'}",
                f"- URL: {data.get('url') or '(missing)'}",
                f"- Tags: {tags_text(data)}",
                "",
                "### Source Identity",
                "",
                f"- Source: {entry.get('source') or '(unknown)'}",
                f"- Source title: {entry.get('sourceTitle') or '(missing)'}",
                f"- Evidence: {evidence_text(entry)}",
                "",
                "### Decision State",
                "",
                f"- Conflict note present: {'yes' if key in documented else 'no'}",
                "- Safe default: keep review/conflict tags until the user chooses an authoritative identity.",
                "- Option A: keep the Zotero title identity and replace the mismatched URL only after an authoritative source for that title is found.",
                "- Option B: treat the URL/source identity as authoritative and apply a guarded metadata repair plan after approval.",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path, help="JSON from 'zot search ... --all --json'")
    parser.add_argument("identity_report", type=Path, help="JSON from identity_audit.py")
    parser.add_argument("--output", type=Path, help="write Markdown report here; defaults to stdout")
    args = parser.parse_args()
    try:
        text = build_report(load_library(args.library), load_identity_report(args.identity_report))
    except ConflictReportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
