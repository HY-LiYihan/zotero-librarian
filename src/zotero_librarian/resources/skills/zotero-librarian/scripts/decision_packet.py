#!/usr/bin/env python3
"""Create a read-only user decision packet for unresolved identity conflicts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from conflict_report import creators_text, evidence_text, item_data, item_key, load_identity_report, load_library, tags_text
from goal_status import build_status


class DecisionPacketError(ValueError):
    pass


def load_plan_report(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionPacketError(f"cannot read source plan report: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise DecisionPacketError("source plan report must be a JSON array")
    return value


def plan_lookup(report: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("key") or ""): item for item in report if item.get("key")}


def build_packet(
    items: list[dict[str, Any]],
    identity_report: list[dict[str, Any]],
    *,
    expected_items: int | None = None,
    source_plan_report: list[dict[str, Any]] | None = None,
) -> str:
    status = build_status(items, expected_items=expected_items)
    lookup = {
        item_key(item): item_data(item)
        for item in items
        if item_key(item) and item_data(item).get("itemType") not in {"annotation", "attachment", "note"}
    }
    conflicts = [entry for entry in identity_report if entry.get("status") == "conflict"]
    source_plans = plan_lookup(source_plan_report or [])
    lines = [
        "# Zotero Identity Decision Packet",
        "",
        "- Writes performed: none",
        f"- Parent count: {status['parentCount']}",
        f"- Expected parent count: {status['expectedParentCount']}",
        f"- Parent count OK: {str(status['parentCountOk']).lower()}",
        f"- Automation complete: {str(status['automationComplete']).lower()}",
        f"- Full complete: {str(status['fullComplete']).lower()}",
        f"- Manual decision required: {str(status['manualDecisionRequired']).lower()}",
        "",
    ]
    if not conflicts:
        lines.extend(["No identity conflicts require a user decision.", ""])
        return "\n".join(lines)

    for entry in conflicts:
        key = str(entry.get("key") or "")
        data = lookup.get(key, {})
        plan = source_plans.get(key)
        lines.extend(
            [
                f"## {key}",
                "",
                "### Current Zotero Identity",
                "",
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
                "### Choices",
                "",
                "- A: Keep the current Zotero title identity. Do not write now; replace the mismatched URL only after an authoritative source for the current title is found.",
                "- B: Adopt the source identity. Generate and preview a guarded source-identity plan, then apply only after explicit approval and backup.",
                "- C: Leave this item in manual review. Keep status:metadata-conflict and status:needs-review.",
                "",
            ]
        )
        if plan:
            lines.extend(
                [
                    "### Prepared Source-Identity Plan",
                    "",
                    f"- Plan status: {plan.get('status')}",
                    f"- Set fields: {', '.join(plan.get('setFields') or []) or '(none)'}",
                    f"- Creator count: {plan.get('creators', 0)}",
                    f"- Remove tags: {', '.join(plan.get('removeTags') or []) or '(none)'}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Required Confirmation",
            "",
            "Reply with one of: A, B, or C. No Zotero write is safe until this decision is explicit.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path, help="JSON from 'zot search ... --all --json'")
    parser.add_argument("identity_report", type=Path, help="JSON from identity_audit.py")
    parser.add_argument("--expect-items", type=int, help="expected parent item count")
    parser.add_argument("--source-plan-report", type=Path, help="optional JSON from source_identity_plan.py --report")
    parser.add_argument("--output", type=Path, help="write Markdown packet here; defaults to stdout")
    args = parser.parse_args()
    try:
        text = build_packet(
            load_library(args.library),
            load_identity_report(args.identity_report),
            expected_items=args.expect_items,
            source_plan_report=load_plan_report(args.source_plan_report),
        )
    except (DecisionPacketError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
