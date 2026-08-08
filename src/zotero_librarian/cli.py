from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9-3.10
    import tomli as tomllib  # type: ignore[no-redef]

from . import __version__
from .core import (
    conflict_report,
    decision_packet,
    goal_status,
    identity_audit,
    librarian_apply,
    librarian_guard,
    library_audit,
    metadata_enricher,
    source_identity_plan,
)
from .schemas import SCHEMAS


CONFIG_PATH = Path.home() / ".config" / "zotero-librarian" / "config.toml"
WRITE_ZOT_COMMANDS = {
    "add",
    "apply",
    "backup",
    "collection",
    "dedupe",
    "enrich",
    "move",
    "note",
    "set",
    "tag",
    "undo",
}


class CliError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.exit_code = exit_code


def emit_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def redact(text: str) -> str:
    token = os.environ.get("ZOTERO_AGENT_TOKEN")
    redacted = text.replace(token, "[REDACTED]") if token else text
    for name in ("ZOTERO_API_KEY", "WEBDAV_PASSWORD", "ZOTERO_AGENT_TOKEN"):
        if name in redacted:
            redacted = redacted.replace(name, f"{name}[redacted-name]")
    return redacted


def run_subprocess(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise CliError("command_failed", f"cannot run {command[0]}: {exc}") from exc


def require_success(result: subprocess.CompletedProcess[str], *, code: str = "command_failed") -> str:
    if result.returncode != 0:
        raise CliError(
            code,
            redact(result.stderr.strip() or result.stdout.strip() or "command failed"),
            details={"returncode": result.returncode},
            exit_code=result.returncode or 1,
        )
    return result.stdout


def parse_json_stdout(text: str, *, code: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(code, f"command did not emit JSON: {exc.msg}") from exc


def run_zot(args: list[str]) -> subprocess.CompletedProcess[str]:
    zot = shutil.which("zot")
    if not zot:
        raise CliError("missing_zot", "cannot find zot on PATH; install zotero-agent first")
    return run_subprocess([zot, *args])


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CliError("invalid_config", f"cannot read config: {exc}") from exc


def skill_root() -> Path:
    return Path(__file__).resolve().parent / "resources" / "skills"


def resolve_skill_resource(resource: str) -> Path:
    root = skill_root().resolve()
    if resource == "zotero-librarian":
        resource = "zotero-librarian/SKILL.md"
    candidate = (root / resource).resolve()
    if root != candidate and root not in candidate.parents:
        raise CliError("invalid_path", "skill resource path escapes embedded skills")
    if not candidate.exists() or candidate.is_dir():
        raise CliError("not_found", f"skill resource not found: {resource}", exit_code=2)
    return candidate


def command_doctor(args: argparse.Namespace) -> int:
    config_error: str | None = None
    try:
        config = load_config(args.config)
    except CliError as exc:
        config = {}
        config_error = exc.message
    zot_path = shutil.which("zot")
    skill_dir = skill_root() / "zotero-librarian"
    installed_codex = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills" / "zotero-librarian"
    checks: dict[str, Any] = {
        "python": {"ok": True, "version": sys.version.split()[0], "executable": sys.executable},
        "package": {"ok": True, "version": __version__},
        "zot": {"ok": bool(zot_path), "path": zot_path},
        "config": {
            "ok": config_error is None,
            "path": str(args.config),
            "present": args.config.exists(),
            "keys": sorted(config.keys()),
            "error": config_error,
        },
        "embeddedSkill": {"ok": skill_dir.exists(), "path": str(skill_dir)},
        "codexSkill": {"ok": installed_codex.exists(), "path": str(installed_codex)},
    }
    if args.offline:
        checks["zoteroBridge"] = {"ok": None, "skipped": True, "reason": "offline"}
    elif zot_path:
        ping = run_zot(["ping"])
        checks["zoteroBridge"] = {
            "ok": ping.returncode == 0,
            "output": redact((ping.stdout or ping.stderr).strip()),
        }
    else:
        checks["zoteroBridge"] = {"ok": False, "skipped": True, "reason": "missing zot"}
    skill_ready = all(
        checks[name].get("ok") is not False
        for name in ("python", "package", "config", "embeddedSkill", "codexSkill")
    )
    live_ready = skill_ready and checks["zot"].get("ok") is True and checks["zoteroBridge"].get("ok") is True
    ready = skill_ready if args.offline else live_ready
    result = {
        "ok": True,
        "ready": ready,
        "skillReady": skill_ready,
        "liveReady": live_ready,
        "offline": args.offline,
        "checks": checks,
    }
    if args.json_output:
        emit_json(result)
    else:
        print(f"zotero-librarian {__version__}")
        for name, check in checks.items():
            state = "SKIP" if check.get("ok") is None else "OK" if check.get("ok") else "FAIL"
            print(f"{name:<14} {state}")
        if ready:
            print()
            if args.offline:
                print("Skill install ready.")
                print("Live Zotero access still requires zotero-agent, the bridge XPI, and running Zotero Desktop.")
            else:
                print("Live Zotero access ready.")
        else:
            target = "skill install" if args.offline else "live Zotero access"
            print(f"Some {target} checks failed; run with --json for details.", file=sys.stderr)
    return 0


def command_schema(args: argparse.Namespace) -> int:
    schema = SCHEMAS.get(args.name)
    if schema is None:
        raise CliError("unknown_schema", f"unknown schema: {args.name}", exit_code=2)
    if args.json_output:
        emit_json({"ok": True, "name": args.name, "schema": schema})
    else:
        print(f"# {args.name}\n")
        print(schema["description"])
        for field, description in schema.get("fields", {}).items():
            print(f"- {field}: {description}")
    return 0


def command_skills_list(args: argparse.Namespace) -> int:
    root = skill_root()
    target = root if not args.path else (root / args.path).resolve()
    if root.resolve() != target and root.resolve() not in target.parents:
        raise CliError("invalid_path", "skill list path escapes embedded skills")
    if not target.exists() or not target.is_dir():
        raise CliError("not_found", f"skill path not found: {args.path}", exit_code=2)
    entries = sorted(path.name + ("/" if path.is_dir() else "") for path in target.iterdir())
    if args.json_output:
        emit_json({"ok": True, "path": args.path or "", "entries": entries})
    else:
        print("\n".join(entries))
    return 0


def command_skills_read(args: argparse.Namespace) -> int:
    path = resolve_skill_resource(args.resource)
    content = path.read_text(encoding="utf-8")
    if args.json_output:
        emit_json({"ok": True, "resource": args.resource, "content": content})
    else:
        sys.stdout.write(content)
    return 0


def copy_skill(destination_root: Path, *, force: bool, dry_run: bool) -> dict[str, Any]:
    source = skill_root() / "zotero-librarian"
    destination = destination_root / "zotero-librarian"
    if dry_run:
        return {"destination": str(destination), "wouldInstall": True, "exists": destination.exists()}
    destination_root.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not force:
            raise CliError("destination_exists", f"refusing to overwrite {destination}; pass --force")
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return {"destination": str(destination), "installed": True}


def skill_install_next_steps(args: argparse.Namespace) -> list[str]:
    steps: list[str] = []
    if args.codex:
        steps.append("Start a new Codex turn so the zotero-librarian skill is discovered.")
    if args.claude:
        steps.append("Restart or refresh Claude Code so the zotero-librarian skill is discovered.")
    steps.append("For live Zotero work, keep Zotero Desktop running and run: uvx zotero-librarian --json doctor")
    steps.append("If you installed the CLI persistently, you can use: zotero-librarian --json doctor")
    return steps


def command_skills_install(args: argparse.Namespace) -> int:
    if not args.codex and not args.claude:
        raise CliError("missing_target", "pass --codex, --claude, or both", exit_code=2)
    results: list[dict[str, Any]] = []
    if args.codex:
        results.append(copy_skill(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills", force=args.force, dry_run=args.dry_run))
    if args.claude:
        results.append(copy_skill(Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude"))) / "skills", force=args.force, dry_run=args.dry_run))
    next_steps = skill_install_next_steps(args)
    if args.json_output:
        emit_json({"ok": True, "dryRun": args.dry_run, "results": results, "nextSteps": next_steps})
    else:
        for result in results:
            verb = "Would install to" if args.dry_run else "Installed to"
            print(f"{verb} {result['destination']}")
        if not args.dry_run:
            print()
            print("Next steps:")
            for step in next_steps:
                print(f"- {step}")
    return 0


def command_library_export(args: argparse.Namespace) -> int:
    output = require_success(run_zot(["search", "", "--all", "--json"]))
    items = parse_json_stdout(output, code="invalid_zot_json")
    if args.out:
        args.out.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        result: dict[str, Any] = {"ok": True, "items": len(items) if isinstance(items, list) else None}
        if args.out:
            result["out"] = str(args.out)
        else:
            result["data"] = items
        emit_json(result)
    else:
        if args.out:
            print(f"Exported {len(items) if isinstance(items, list) else 'unknown'} items to {args.out}")
        else:
            sys.stdout.write(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
    return 0


def command_library_audit(args: argparse.Namespace) -> int:
    result = library_audit.audit(library_audit.load_items(args.input))
    errors: list[str] = []
    if args.expect_items is not None and result["parents"] != args.expect_items:
        errors.append(f"expected {args.expect_items} parent items, found {result['parents']}")
    if args.strict:
        errors.extend(library_audit.strict_errors(result, allow_documented_conflicts=args.allow_documented_conflicts))
    payload = {"ok": not errors, **result, "errors": errors}
    if args.json_output:
        emit_json(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def command_library_status(args: argparse.Namespace) -> int:
    status = goal_status.build_status(library_audit.load_items(args.input), expected_items=args.expect_items)
    payload = {"ok": True, **status}
    if args.json_output:
        emit_json(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status["fullComplete"] else 1


def command_identity_audit(args: argparse.Namespace) -> int:
    keys = set(args.keys.split(",")) if args.keys else None
    report = identity_audit.audit_identity(
        identity_audit.load_items(args.input),
        timeout=args.timeout,
        delay=args.delay,
        include_doi_field=args.include_doi_field,
        keys=keys,
        workers=max(1, args.workers),
    )
    output_report = [entry for entry in report if entry["status"] == "conflict"] if args.only_conflicts else report
    result = {
        "ok": True,
        "itemsChecked": len(report),
        "conflicts": sum(1 for entry in report if entry["status"] == "conflict"),
        "unresolved": sum(1 for entry in report if entry["status"] == "unresolved"),
        "report": output_report,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    if args.json_output:
        if args.output:
            emit_json({**result, "output": str(args.output)})
        else:
            emit_json(result)
    elif args.output:
        print(f"Wrote identity audit to {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def command_identity_report(args: argparse.Namespace) -> int:
    text = conflict_report.build_report(
        conflict_report.load_library(args.library),
        conflict_report.load_identity_report(args.identity_report),
    )
    return emit_text_or_file(text, args.output, args)


def command_identity_decision(args: argparse.Namespace) -> int:
    text = decision_packet.build_packet(
        decision_packet.load_library(args.library),
        decision_packet.load_identity_report(args.identity_report),
        expected_items=args.expect_items,
        source_plan_report=decision_packet.load_plan_report(args.source_plan_report),
    )
    return emit_text_or_file(text, args.output, args)


def command_identity_plan(args: argparse.Namespace) -> int:
    edits, report = source_identity_plan.build_source_identity_plan(
        source_identity_plan.load_library(args.library),
        source_identity_plan.load_identity_report(args.identity_report),
        timeout=args.timeout,
    )
    plan_text = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in edits)
    if args.output:
        args.output.write_text(plan_text, encoding="utf-8")
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        emit_json({"ok": True, "planned": len(edits), "unresolved": len(report) - len(edits), "output": str(args.output) if args.output else None, "report": str(args.report) if args.report else None, "edits": [] if args.output else edits})
    elif args.output:
        print(f"planned={len(edits)} unresolved={len(report) - len(edits)} output={args.output}")
    else:
        sys.stdout.write(plan_text)
    return 0


def emit_text_or_file(text: str, output: Path | None, args: argparse.Namespace) -> int:
    if output:
        output.write_text(text, encoding="utf-8")
    if args.json_output:
        emit_json({"ok": True, "output": str(output) if output else None, "content": None if output else text})
    elif output:
        print(f"Wrote {output}")
    else:
        sys.stdout.write(text)
    return 0


def command_metadata_enrich(args: argparse.Namespace) -> int:
    items = metadata_enricher.load_items(args.input)
    if args.field == "doi":
        plan, report = metadata_enricher.build_doi_plan(items, search=args.search_doi, timeout=args.timeout, delay=args.delay)
    else:
        plan, report = metadata_enricher.build_plan(items, timeout=args.timeout, delay=args.delay)
    plan_text = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in plan)
    if args.output:
        args.output.write_text(plan_text, encoding="utf-8")
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        emit_json({"ok": True, "field": args.field, "planned": len(plan), "unresolved": len(report) - len(plan), "output": str(args.output) if args.output else None, "report": str(args.report) if args.report else None, "plan": [] if args.output else plan})
    elif args.output:
        print(f"planned={len(plan)} unresolved={len(report) - len(plan)} output={args.output}")
    else:
        sys.stdout.write(plan_text)
    return 0


def command_plan_validate(args: argparse.Namespace) -> int:
    taxonomy = librarian_guard.load_toml(args.taxonomy)
    taxonomy_errors = librarian_guard.validate_taxonomy(taxonomy)
    if taxonomy_errors:
        payload = {"ok": False, "file": str(args.file), "taxonomy": str(args.taxonomy), "errors": taxonomy_errors}
    else:
        item_types = librarian_guard.load_item_types(args.library_json)
        errors, entries, trash_entries = librarian_guard.validate_plan(args.file, taxonomy, item_types)
        payload = {"ok": not errors, "file": str(args.file), "taxonomy": str(args.taxonomy), "entries": entries, "trash_entries": trash_entries, "errors": errors}
    if args.json_output:
        emit_json(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def command_plan_preview(args: argparse.Namespace) -> int:
    if args.extended:
        edits = librarian_apply.load_edits(args.file)
        errors = librarian_apply.validate_edits(edits)
        if errors:
            raise CliError("invalid_plan", "; ".join(errors), exit_code=1)
        result = librarian_apply.dry_run_summary(edits)
    else:
        output = require_success(run_zot(["apply", str(args.file), "--dry-run", "--json"]))
        result = parse_json_stdout(output, code="invalid_zot_json")
    if args.json_output:
        emit_json(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_plan_sample(args: argparse.Namespace) -> int:
    lines = [line for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    selected = lines[: args.count]
    args.out.write_text("\n".join(selected) + ("\n" if selected else ""), encoding="utf-8")
    payload = {"ok": True, "input": str(args.file), "out": str(args.out), "count": len(selected)}
    if args.json_output:
        emit_json(payload)
    else:
        print(f"Wrote {len(selected)} plan entries to {args.out}")
    return 0


def command_plan_apply(args: argparse.Namespace) -> int:
    if not args.yes:
        raise CliError("confirmation_required", "refusing to write without --yes; run plan preview first")
    backup_text = require_success(run_zot(["backup"]), code="backup_failed")
    if args.extended:
        apply_cmd = [sys.executable, "-m", "zotero_librarian.core.librarian_apply", str(args.file), "--yes", "--json"]
        output = require_success(run_subprocess(apply_cmd), code="apply_failed")
    else:
        output = require_success(run_zot(["apply", str(args.file), "--yes", "--json"]), code="apply_failed")
    try:
        apply_result = json.loads(output)
    except json.JSONDecodeError:
        apply_result = {"raw": output.strip()}
    payload = {"ok": True, "backup": backup_text.strip(), "result": apply_result}
    if args.json_output:
        emit_json(payload)
    else:
        print(backup_text.strip())
        print(json.dumps(apply_result, ensure_ascii=False, indent=2))
    return 0 if apply_result.get("ok", True) else 1


def command_item_get(args: argparse.Namespace) -> int:
    output = require_success(run_zot(["get", args.key, "--json"]))
    return emit_subprocess_json(output, args)


def command_item_pdf(args: argparse.Namespace) -> int:
    output = require_success(run_zot(["pdf", args.key]))
    path = output.strip()
    if args.json_output:
        emit_json({"ok": True, "key": args.key, "path": path})
    else:
        print(path)
    return 0


def command_item_notes(args: argparse.Namespace) -> int:
    output = require_success(run_zot(["notes", args.key, "--json"]))
    return emit_subprocess_json(output, args)


def emit_subprocess_json(output: str, args: argparse.Namespace) -> int:
    if args.json_output:
        emit_json(parse_json_stdout(output, code="invalid_zot_json"))
    else:
        sys.stdout.write(output)
    return 0


def command_raw_zot(args: argparse.Namespace) -> int:
    zot_args = list(args.zot_args)
    if zot_args and zot_args[0] == "--":
        zot_args = zot_args[1:]
    if not zot_args:
        raise CliError("missing_args", "pass zot arguments after `raw zot --`", exit_code=2)
    if zot_args[0] == "exec":
        raise CliError("forbidden_raw_command", "zot exec is never allowed through zotero-librarian")
    if zot_args[0] in WRITE_ZOT_COMMANDS and not args.allow_write:
        raise CliError("write_confirmation_required", f"raw zot {zot_args[0]} requires --allow-write")
    result = run_zot(zot_args)
    output = require_success(result)
    if args.json_output:
        try:
            emit_json({"ok": True, "command": zot_args, "data": json.loads(output)})
        except json.JSONDecodeError:
            emit_json({"ok": True, "command": zot_args, "stdout": output})
    else:
        sys.stdout.write(output)
    return 0


def add_common_library_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="JSON from 'zot search ... --all --json'")
    parser.add_argument("--expect-items", type=int, help="expected parent item count")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zotero-librarian",
        description="Safety-first CLI and Agent skill for local Zotero Desktop library maintenance.",
    )
    parser.add_argument("--json", dest="json_output", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--version", action="version", version=f"zotero-librarian {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check package, zot, skill, config, and bridge readiness")
    doctor.add_argument("--offline", action="store_true", help="skip live Zotero bridge checks")
    doctor.add_argument("--config", type=Path, default=CONFIG_PATH, help="non-secret config path")
    doctor.set_defaults(func=command_doctor)

    schema = sub.add_parser("schema", help="show JSON shapes for agent-facing outputs")
    schema.add_argument("name", choices=sorted(SCHEMAS))
    schema.set_defaults(func=command_schema)

    skills = sub.add_parser("skills", help="read or install embedded Agent skill resources")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    skills_list = skills_sub.add_parser("list", help="list embedded skills or resources")
    skills_list.add_argument("path", nargs="?", default="")
    skills_list.set_defaults(func=command_skills_list)
    skills_read = skills_sub.add_parser("read", help="print an embedded skill resource")
    skills_read.add_argument("resource", help="zotero-librarian or zotero-librarian/<path>")
    skills_read.set_defaults(func=command_skills_read)
    skills_install = skills_sub.add_parser("install", help="install embedded skill for Agent clients")
    skills_install.add_argument("--codex", action="store_true")
    skills_install.add_argument("--claude", action="store_true")
    skills_install.add_argument("--force", action="store_true")
    skills_install.add_argument("--dry-run", action="store_true")
    skills_install.set_defaults(func=command_skills_install)

    library = sub.add_parser("library", help="export, audit, and summarize Zotero libraries")
    library_sub = library.add_subparsers(dest="library_command", required=True)
    export = library_sub.add_parser("export", help="export the full Zotero library through zot")
    export.add_argument("--out", type=Path, help="write JSON export here")
    export.set_defaults(func=command_library_export)
    audit = library_sub.add_parser("audit", help="audit a full library JSON export")
    add_common_library_args(audit)
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--allow-documented-conflicts", action="store_true")
    audit.set_defaults(func=command_library_audit)
    status = library_sub.add_parser("status", help="summarize completion gates from a full export")
    add_common_library_args(status)
    status.set_defaults(func=command_library_status)

    identity = sub.add_parser("identity", help="audit and repair URL/DOI-backed identity conflicts")
    identity_sub = identity.add_subparsers(dest="identity_command", required=True)
    iaudit = identity_sub.add_parser("audit", help="read-only identity conflict audit")
    iaudit.add_argument("input", type=Path)
    iaudit.add_argument("--timeout", type=float, default=20.0)
    iaudit.add_argument("--delay", type=float, default=0.1)
    iaudit.add_argument("--output", type=Path)
    iaudit.add_argument("--only-conflicts", action="store_true")
    iaudit.add_argument("--keys", help="comma-separated item keys")
    iaudit.add_argument("--workers", type=int, default=1)
    iaudit.add_argument("--include-doi-field", action="store_true")
    iaudit.set_defaults(func=command_identity_audit)
    ireport = identity_sub.add_parser("report", help="build a Markdown conflict report")
    ireport.add_argument("library", type=Path)
    ireport.add_argument("identity_report", type=Path)
    ireport.add_argument("--output", type=Path)
    ireport.set_defaults(func=command_identity_report)
    idecision = identity_sub.add_parser("decision", help="build a user-facing identity decision packet")
    idecision.add_argument("library", type=Path)
    idecision.add_argument("identity_report", type=Path)
    idecision.add_argument("--expect-items", type=int)
    idecision.add_argument("--source-plan-report", type=Path)
    idecision.add_argument("--output", type=Path)
    idecision.set_defaults(func=command_identity_decision)
    iplan = identity_sub.add_parser("plan", help="generate a guarded source-identity JSONL plan")
    iplan.add_argument("library", type=Path)
    iplan.add_argument("identity_report", type=Path)
    iplan.add_argument("--output", type=Path)
    iplan.add_argument("--report", type=Path)
    iplan.add_argument("--timeout", type=float, default=20.0)
    iplan.set_defaults(func=command_identity_plan)

    metadata = sub.add_parser("metadata", help="generate safe metadata enrichment plans")
    metadata_sub = metadata.add_subparsers(dest="metadata_command", required=True)
    enrich = metadata_sub.add_parser("enrich", help="build abstract or DOI enrichment JSONL")
    enrich.add_argument("input", type=Path)
    enrich.add_argument("--field", choices=("abstract", "doi"), default="abstract")
    enrich.add_argument("--search-doi", action="store_true")
    enrich.add_argument("--output", type=Path)
    enrich.add_argument("--report", type=Path)
    enrich.add_argument("--timeout", type=float, default=20.0)
    enrich.add_argument("--delay", type=float, default=0.1)
    enrich.set_defaults(func=command_metadata_enrich)

    plan = sub.add_parser("plan", help="validate, preview, sample, and apply JSONL plans")
    plan_sub = plan.add_subparsers(dest="plan_command", required=True)
    validate = plan_sub.add_parser("validate", help="validate a plan against a taxonomy")
    validate.add_argument("file", type=Path)
    validate.add_argument("--taxonomy", type=Path, required=True)
    validate.add_argument("--library-json", type=Path)
    validate.set_defaults(func=command_plan_validate)
    preview = plan_sub.add_parser("preview", help="dry-run a plan")
    preview.add_argument("file", type=Path)
    preview.add_argument("--extended", action="store_true", help="use guarded creator/item-type preview")
    preview.set_defaults(func=command_plan_preview)
    sample = plan_sub.add_parser("sample", help="write the first N plan entries to a new JSONL file")
    sample.add_argument("file", type=Path)
    sample.add_argument("--out", type=Path, required=True)
    sample.add_argument("--count", type=int, default=2)
    sample.set_defaults(func=command_plan_sample)
    apply = plan_sub.add_parser("apply", help="backup then apply a reviewed plan")
    apply.add_argument("file", type=Path)
    apply.add_argument("--yes", action="store_true")
    apply.add_argument("--extended", action="store_true", help="use guarded creator/item-type applier")
    apply.set_defaults(func=command_plan_apply)

    item = sub.add_parser("item", help="read exact Zotero items, PDFs, and notes")
    item_sub = item.add_subparsers(dest="item_command", required=True)
    get = item_sub.add_parser("get", help="read a Zotero item as JSON")
    get.add_argument("key")
    get.set_defaults(func=command_item_get)
    pdf = item_sub.add_parser("pdf", help="print the local PDF path for an item")
    pdf.add_argument("key")
    pdf.set_defaults(func=command_item_pdf)
    notes = item_sub.add_parser("notes", help="read child notes as JSON")
    notes.add_argument("key")
    notes.set_defaults(func=command_item_notes)

    raw = sub.add_parser("raw", help="escape hatch for direct zot commands")
    raw_sub = raw.add_subparsers(dest="raw_command", required=True)
    raw_zot = raw_sub.add_parser("zot", help="run zot with safety gates")
    raw_zot.add_argument("--allow-write", action="store_true", help="required for known write commands")
    raw_zot.add_argument("zot_args", nargs=argparse.REMAINDER)
    raw_zot.set_defaults(func=command_raw_zot)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        func: Callable[[argparse.Namespace], int] = args.func
        return func(args)
    except CliError as exc:
        if getattr(args, "json_output", False):
            emit_json({"ok": False, "error": {"code": exc.code, "message": exc.message, "details": exc.details}})
        else:
            print(exc.message, file=sys.stderr)
        return exc.exit_code
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        message = redact(str(exc))
        if getattr(args, "json_output", False):
            emit_json({"ok": False, "error": {"code": "runtime_error", "message": message}})
        else:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
