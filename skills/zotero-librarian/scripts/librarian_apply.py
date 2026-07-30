#!/usr/bin/env python3
"""Apply Zotero Librarian extended JSONL edits through the zotero-agent bridge.

This script is intentionally narrow. Use upstream `zot apply` for ordinary field,
tag, collection, and Trash plans. Use this script only for top-level
`setCreators` and `setItemType` repairs plus optional field/tag changes in the same undoable snapshot.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any


ITEM_KEY = re.compile(r"^[A-Z0-9]{8}$")
ALLOWED_FIELDS = {"key", "set", "setCreators", "setItemType", "addTags", "removeTags"}
ALLOWED_ITEM_TYPES = {
    "bookSection",
    "conferencePaper",
    "dataset",
    "document",
    "journalArticle",
    "preprint",
    "report",
    "webpage",
}
UNSUPPORTED_SET_FIELDS = {"collections", "creators", "relations", "tags", "itemType"}


class ApplyError(ValueError):
    pass


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "errors": [message]}, ensure_ascii=False, indent=2)


def load_edits(path: Path) -> list[dict[str, Any]]:
    try:
        raw = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ApplyError(f"cannot read plan: {exc}") from exc
    edits: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ApplyError(f"line {number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ApplyError(f"line {number}: entry must be a JSON object")
        edits.append(value)
    if not edits:
        raise ApplyError("plan contains no entries")
    return edits


def validate_creator(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["creator entries must be objects"]
    allowed = {"creatorType", "firstName", "lastName", "name"}
    errors: list[str] = []
    unknown = set(value) - allowed
    if unknown:
        errors.append(f"unsupported creator fields: {', '.join(sorted(unknown))}")
    creator_type = value.get("creatorType")
    if not isinstance(creator_type, str) or not creator_type.strip():
        errors.append("creatorType must be a non-empty string")
    has_name = "name" in value
    has_parts = "firstName" in value or "lastName" in value
    if has_name and has_parts:
        errors.append("single-field creators must not mix name with firstName/lastName")
    if has_name:
        if not isinstance(value.get("name"), str) or not value.get("name", "").strip():
            errors.append("name must be a non-empty string")
    else:
        last_name = value.get("lastName")
        if not isinstance(last_name, str) or not last_name.strip():
            errors.append("lastName must be a non-empty string")
        if "firstName" in value and not isinstance(value.get("firstName"), str):
            errors.append("firstName must be a string when present")
    return errors


def validate_edits(edits: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_keys: set[str] = set()
    for number, edit in enumerate(edits, 1):
        prefix = f"line {number}"
        unknown = set(edit) - ALLOWED_FIELDS
        if unknown:
            errors.append(f"{prefix}: unsupported fields: {', '.join(sorted(unknown))}")
        key = edit.get("key")
        if not isinstance(key, str) or not ITEM_KEY.fullmatch(key):
            errors.append(f"{prefix}: key must be an 8-character uppercase Zotero item key")
        elif key in seen_keys:
            errors.append(f"{prefix}: duplicate item key {key}")
        elif key:
            seen_keys.add(key)
        if len(edit) == 1 and "key" in edit:
            errors.append(f"{prefix}: entry contains no change")
        if "set" in edit:
            values = edit["set"]
            if not isinstance(values, dict) or not values:
                errors.append(f"{prefix}: set must be a non-empty object")
            else:
                unsupported = set(values) & UNSUPPORTED_SET_FIELDS
                if unsupported:
                    errors.append(f"{prefix}: unsupported set fields: {', '.join(sorted(unsupported))}")
        if "setItemType" in edit:
            item_type = edit["setItemType"]
            if not isinstance(item_type, str) or item_type not in ALLOWED_ITEM_TYPES:
                errors.append(f"{prefix}: setItemType must be one of {sorted(ALLOWED_ITEM_TYPES)}")
        if "setCreators" in edit:
            creators = edit["setCreators"]
            if not isinstance(creators, list) or not creators:
                errors.append(f"{prefix}: setCreators must be a non-empty list")
            else:
                for index, creator in enumerate(creators, 1):
                    for error in validate_creator(creator):
                        errors.append(f"{prefix}: setCreators[{index}]: {error}")
        for field in ("addTags", "removeTags"):
            if field not in edit:
                continue
            tags = edit[field]
            if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
                errors.append(f"{prefix}: {field} must be a list of non-empty strings")
            elif len(tags) != len(set(tags)):
                errors.append(f"{prefix}: {field} contains duplicates")
    return errors


def dry_run_summary(edits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": True,
        "dryRun": True,
        "edits": len(edits),
        "keys": [edit["key"] for edit in edits],
        "operations": [
            {
                "key": edit["key"],
                "setItemType": edit.get("setItemType"),
                "set": sorted(edit.get("set", {})),
                "setCreators": len(edit.get("setCreators", [])),
                "addTags": edit.get("addTags", []),
                "removeTags": edit.get("removeTags", []),
            }
            for edit in edits
        ],
    }


def reexec_with_zot_python() -> None:
    if importlib.util.find_spec("zotero_agent"):
        return
    if os.environ.get("ZOTERO_LIBRARIAN_REEXECED") == "1":
        raise ApplyError("cannot import zotero_agent with the zot Python runtime")
    zot = shutil.which("zot")
    if not zot:
        raise ApplyError("cannot find zot; install zotero-agent first")
    try:
        first_line = Path(zot).read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    except (OSError, IndexError) as exc:
        raise ApplyError(f"cannot inspect zot executable: {exc}") from exc
    if not first_line.startswith("#!"):
        raise ApplyError("cannot locate zot Python runtime from executable shebang")
    command = shlex.split(first_line[2:].strip())
    if not command:
        raise ApplyError("cannot locate zot Python runtime from executable shebang")
    env = {**os.environ, "ZOTERO_LIBRARIAN_REEXECED": "1"}
    os.execve(command[0], command + [__file__, *sys.argv[1:]], env)


def apply_edits(edits: list[dict[str, Any]]) -> dict[str, Any]:
    reexec_with_zot_python()
    from zotero_agent.commands.features import _snapshot
    from zotero_agent.config import require_config
    from zotero_agent.http import run_js

    cfg = require_config(None)
    keys = [edit["key"] for edit in edits]
    op_id = _snapshot(cfg, keys, "librarian-apply")
    code = (
        "var edits=%s; var lib=Zotero.Libraries.userLibraryID; var applied=0, errors=[];\n"
        "function targetTypeID(it, e){\n"
        "  if(!e.setItemType) return it.itemTypeID;\n"
        "  var id = Zotero.ItemTypes.getID(e.setItemType);\n"
        "  if(!id) throw new Error('invalid item type: '+e.setItemType);\n"
        "  return id;\n"
        "}\n"
        "function validateSetFields(it, e){\n"
        "  if(!e.set) return;\n"
        "  var typeID = targetTypeID(it, e);\n"
        "  for (var f in e.set){\n"
        "    var fieldID = Zotero.ItemFields.getID(f);\n"
        "    if(!fieldID) throw new Error('unknown field: '+f);\n"
        "    if(Zotero.ItemFields.isBaseField(fieldID)){\n"
        "      var mapped = Zotero.ItemFields.getFieldIDFromTypeAndBase(typeID, fieldID);\n"
        "      if(mapped) fieldID = mapped;\n"
        "    }\n"
        "    if(!Zotero.ItemFields.isValidForType(fieldID, typeID)){\n"
        "      throw new Error('field '+f+' is not valid for target item type');\n"
        "    }\n"
        "  }\n"
        "}\n"
        "await Zotero.DB.executeTransaction(async function(){\n"
        "  for (var e of edits){\n"
        "    var it=await Zotero.Items.getByLibraryAndKeyAsync(lib, e.key);\n"
        "    if(!it){ errors.push(e.key+': not found'); continue; }\n"
        "    try {\n"
        "      validateSetFields(it, e);\n"
        "      if(e.setItemType){ it.setType(targetTypeID(it, e)); }\n"
        "      if(e.set){ for(var f in e.set){ it.setField(f, e.set[f]); } }\n"
        "      if(e.setCreators){ it.setCreators(e.setCreators); }\n"
        "      if(e.addTags){ e.addTags.forEach(function(t){ it.addTag(t); }); }\n"
        "      if(e.removeTags){ e.removeTags.forEach(function(t){ it.removeTag(t); }); }\n"
        "      await it.save(); applied++;\n"
        "    } catch(err){ errors.push(e.key+': '+err); }\n"
        "  }\n"
        "});\n"
        "return { applied: applied, errors: errors };"
    ) % json.dumps(edits, ensure_ascii=False)
    result = run_js(cfg, code, label="librarian-apply")
    result["opId"] = op_id
    result["ok"] = not result.get("errors")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="JSONL file, or '-' for stdin")
    parser.add_argument("--dry-run", action="store_true", help="preview writes without connecting to Zotero")
    parser.add_argument("--yes", action="store_true", help="apply the plan without prompting")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    try:
        edits = load_edits(args.file)
        errors = validate_edits(edits)
        if errors:
            raise ApplyError("; ".join(errors))
        if args.dry_run:
            result = dry_run_summary(edits)
        else:
            if not args.yes:
                raise ApplyError("refusing to write without --yes; run --dry-run first")
            result = apply_edits(edits)
    except ApplyError as exc:
        if args.json:
            print(_json_error(str(exc)))
        else:
            print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.dry_run:
        print(f"DRY-RUN — would apply {result['edits']} extended edit(s).")
        for operation in result["operations"][:5]:
            pieces = []
            if operation["setItemType"]:
                pieces.append(f"setItemType={operation['setItemType']}")
            if operation["set"]:
                pieces.append("set " + ",".join(operation["set"]))
            if operation["setCreators"]:
                pieces.append(f"setCreators[{operation['setCreators']}]")
            if operation["addTags"]:
                pieces.append(f"+tags {operation['addTags']}")
            if operation["removeTags"]:
                pieces.append(f"-tags {operation['removeTags']}")
            print(f"  {operation['key']:<10} {'; '.join(pieces)}")
    else:
        print(f"Applied {result.get('applied', 0)} extended edit(s).")
        if result.get("opId"):
            print(f"Undo with: zot undo {result['opId']}")
        if result.get("errors"):
            print("errors: " + "; ".join(map(str, result["errors"])))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
