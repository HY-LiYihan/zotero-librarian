#!/usr/bin/env python3
"""Validate Zotero Librarian taxonomies and zot apply JSONL plans."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9-3.10
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


ITEM_KEY = re.compile(r"^[A-Z0-9]{8}$")
ALLOWED_PLAN_FIELDS = {
    "key",
    "set",
    "addTags",
    "removeTags",
    "addToCollection",
    "trash",
}
FORBIDDEN_WORDS = {"erase", "eraseTx", "deletePermanently", "emptyTrash"}


class ValidationError(ValueError):
    pass


def load_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise ValidationError("Python <3.11 requires the 'tomli' package")
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValidationError(f"cannot read taxonomy: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("taxonomy must be a TOML table")
    return value


def validate_taxonomy(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("version") != 1:
        errors.append("version must be 1")

    collections = data.get("collections")
    if not isinstance(collections, dict) or not collections:
        errors.append("[collections] must define at least one named collection")
    elif any(not isinstance(v, str) or not v.strip() for v in collections.values()):
        errors.append("collection values must be non-empty strings")

    tags = data.get("tags")
    if not isinstance(tags, dict):
        errors.append("[tags] is required")
    else:
        prefixes = tags.get("allowed_prefixes")
        if not isinstance(prefixes, list) or any(not isinstance(v, str) or not v for v in prefixes):
            errors.append("tags.allowed_prefixes must be a list of non-empty strings")
        exclusive = tags.get("exclusive", {})
        if not isinstance(exclusive, dict):
            errors.append("[tags.exclusive] must be a table")
        else:
            for group, values in exclusive.items():
                if not isinstance(values, list) or len(values) != len(set(values)):
                    errors.append(f"exclusive group {group!r} must contain unique values")
                elif any(not isinstance(v, str) or ":" not in v for v in values):
                    errors.append(f"exclusive group {group!r} values must be namespaced tags")

    policy = data.get("policy")
    if not isinstance(policy, dict):
        errors.append("[policy] is required")
    else:
        if policy.get("deletion") != "trash-only":
            errors.append("policy.deletion must be 'trash-only'")
        if policy.get("attachment_mode") not in {"stored", "linked-explicit-only"}:
            errors.append("policy.attachment_mode must be 'stored' or 'linked-explicit-only'")
    return errors


def taxonomy_rules(data: dict[str, Any]) -> tuple[set[str], bool, dict[str, set[str]]]:
    tags = data.get("tags", {})
    prefixes = {str(v) for v in tags.get("allowed_prefixes", [])}
    allow_unprefixed = bool(tags.get("allow_unprefixed", False))
    groups = {
        str(name): {str(v) for v in values}
        for name, values in tags.get("exclusive", {}).items()
        if isinstance(values, list)
    }
    return prefixes, allow_unprefixed, groups


def validate_tag(tag: Any, prefixes: set[str], allow_unprefixed: bool) -> str | None:
    if not isinstance(tag, str) or not tag.strip():
        return "tag must be a non-empty string"
    if any(word.casefold() in tag.casefold() for word in FORBIDDEN_WORDS):
        return "tag contains permanent-delete vocabulary"
    if ":" not in tag:
        return None if allow_unprefixed else "unprefixed tags are disabled"
    prefix, value = tag.split(":", 1)
    if prefix not in prefixes:
        return f"prefix {prefix!r} is not allowed"
    if not value.strip():
        return "tag value cannot be empty"
    return None


def validate_plan_line(
    value: Any,
    line_number: int,
    taxonomy: dict[str, Any],
) -> list[str]:
    prefix = f"line {line_number}"
    if not isinstance(value, dict):
        return [f"{prefix}: entry must be a JSON object"]
    errors: list[str] = []
    unknown = set(value) - ALLOWED_PLAN_FIELDS
    if unknown:
        errors.append(f"{prefix}: unsupported fields: {', '.join(sorted(unknown))}")
    key = value.get("key")
    if not isinstance(key, str) or not ITEM_KEY.fullmatch(key):
        errors.append(f"{prefix}: key must be an 8-character uppercase Zotero item key")
    if len(value) == 1 and "key" in value:
        errors.append(f"{prefix}: entry contains no change")

    if "set" in value and not isinstance(value["set"], dict):
        errors.append(f"{prefix}: set must be an object")
    if "trash" in value and not isinstance(value["trash"], bool):
        errors.append(f"{prefix}: trash must be boolean")
    if "addToCollection" in value and (
        not isinstance(value["addToCollection"], str) or not value["addToCollection"].strip()
    ):
        errors.append(f"{prefix}: addToCollection must be a non-empty collection name")

    prefixes, allow_unprefixed, groups = taxonomy_rules(taxonomy)
    for field in ("addTags", "removeTags"):
        if field not in value:
            continue
        tags = value[field]
        if not isinstance(tags, list):
            errors.append(f"{prefix}: {field} must be a list")
            continue
        if len(tags) != len(set(str(tag) for tag in tags)):
            errors.append(f"{prefix}: {field} contains duplicates")
        for tag in tags:
            reason = validate_tag(tag, prefixes, allow_unprefixed)
            if reason:
                errors.append(f"{prefix}: invalid {field} tag {tag!r}: {reason}")

    added = set(value.get("addTags", [])) if isinstance(value.get("addTags", []), list) else set()
    for name, members in groups.items():
        selected = added & members
        if len(selected) > 1:
            errors.append(f"{prefix}: exclusive group {name!r} has multiple added tags: {sorted(selected)}")

    serialized = json.dumps(value, ensure_ascii=True)
    for word in FORBIDDEN_WORDS:
        if word.casefold() in serialized.casefold():
            errors.append(f"{prefix}: permanent-delete operation {word!r} is forbidden")
    return errors


def validate_plan(path: Path, taxonomy: dict[str, Any]) -> tuple[list[str], int, int]:
    errors: list[str] = []
    count = 0
    trash_count = 0
    seen_keys: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot read plan: {exc}"], 0, 0
    for number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        count += 1
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: invalid JSON: {exc.msg}")
            continue
        errors.extend(validate_plan_line(value, number, taxonomy))
        if isinstance(value, dict):
            key = value.get("key")
            if isinstance(key, str):
                if key in seen_keys:
                    errors.append(f"line {number}: duplicate item key {key}")
                seen_keys.add(key)
            if value.get("trash") is True:
                trash_count += 1
    if count == 0:
        errors.append("plan contains no entries")
    return errors, count, trash_count


def emit(ok: bool, errors: list[str], **summary: Any) -> int:
    print(json.dumps({"ok": ok, **summary, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    taxonomy_parser = sub.add_parser("taxonomy", help="validate a taxonomy TOML file")
    taxonomy_parser.add_argument("file", type=Path)
    plan_parser = sub.add_parser("plan", help="validate a zot apply JSONL plan")
    plan_parser.add_argument("file", type=Path)
    plan_parser.add_argument("--taxonomy", type=Path, required=True)
    args = parser.parse_args()

    try:
        taxonomy_path = args.file if args.command == "taxonomy" else args.taxonomy
        taxonomy = load_toml(taxonomy_path)
    except ValidationError as exc:
        return emit(False, [str(exc)])
    taxonomy_errors = validate_taxonomy(taxonomy)
    if args.command == "taxonomy":
        return emit(not taxonomy_errors, taxonomy_errors, file=str(args.file))
    if taxonomy_errors:
        return emit(False, taxonomy_errors, file=str(args.file), taxonomy=str(args.taxonomy))
    errors, entries, trash_entries = validate_plan(args.file, taxonomy)
    return emit(
        not errors,
        errors,
        file=str(args.file),
        taxonomy=str(args.taxonomy),
        entries=entries,
        trash_entries=trash_entries,
    )


if __name__ == "__main__":
    sys.exit(main())
