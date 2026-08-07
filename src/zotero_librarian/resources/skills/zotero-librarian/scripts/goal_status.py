#!/usr/bin/env python3
"""Summarize Zotero Librarian goal completion from a full local library export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from library_audit import AuditError, audit, load_items, strict_errors


MANUAL_DECISION_FIELDS = ("metadataConflictDocumented",)


class GoalStatusError(ValueError):
    pass


def build_status(items: list[dict[str, Any]], *, expected_items: int | None = None) -> dict[str, Any]:
    result = audit(items)
    errors: list[str] = []
    if expected_items is not None and result["parents"] != expected_items:
        errors.append(f"expected {expected_items} parent items, found {result['parents']}")
    full_errors = [*errors, *strict_errors(result)]
    automation_errors = [*errors, *strict_errors(result, allow_documented_conflicts=True)]
    manual_decisions = sorted(
        set(result["findings"]["metadataConflictDocumented"])
        & set(result["findings"]["needsReview"])
    )
    return {
        "parentCount": result["parents"],
        "expectedParentCount": expected_items,
        "parentCountOk": not errors,
        "fullComplete": not full_errors,
        "automationComplete": not automation_errors,
        "manualDecisionRequired": bool(manual_decisions),
        "manualDecisionItems": manual_decisions,
        "fullErrors": full_errors,
        "automationErrors": automation_errors,
        "counts": result["counts"],
        "nextActions": next_actions(manual_decisions, full_errors, automation_errors),
    }


def next_actions(
    manual_decisions: list[str],
    full_errors: list[str],
    automation_errors: list[str],
) -> list[str]:
    actions: list[str] = []
    if automation_errors:
        actions.append("Fix remaining actionable audit errors before treating the library as automation-complete.")
    if manual_decisions:
        actions.append(
            "Resolve documented metadata conflicts by choosing the current Zotero identity or the authoritative source identity."
        )
    if not full_errors:
        actions.append("Full strict completion gate is clean.")
    elif not automation_errors and manual_decisions:
        actions.append("No Zotero write is safe without explicit user approval for the identity decision.")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON from 'zot search ... --all --json'")
    parser.add_argument("--expect-items", type=int, help="expected parent item count")
    args = parser.parse_args()
    try:
        status = build_status(load_items(args.input), expected_items=args.expect_items)
    except (AuditError, GoalStatusError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
        return 2
    print(json.dumps({"ok": True, **status}, ensure_ascii=False, indent=2))
    return 0 if status["fullComplete"] else 1


if __name__ == "__main__":
    sys.exit(main())
