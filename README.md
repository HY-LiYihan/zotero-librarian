# Zotero Librarian

Zotero Librarian is a release-ready Python CLI and companion Agent skill for safely auditing, organizing, and maintaining a local Zotero Desktop library. It builds a lark-cli-style command layer on top of the MIT-licensed [`zotero-agent`](https://github.com/alex-roc/zotero-agent) backend: high-level commands, stable JSON, dry-run-first edits, embedded skill resources, and explicit backup/undo rules.

[简体中文](README.zh-CN.md)

## Why this project

`zotero-agent` already handles local Zotero reads and authenticated bridge writes inside a running Zotero process. Zotero Librarian deliberately does not replace that bridge. It turns those primitives into repeatable Agent workflows:

- audit collections, tags, metadata, duplicates, and attachments;
- generate reviewable JSONL edit plans with policy validation;
- classify papers using a user-owned taxonomy;
- repair metadata only when source identity is verified;
- maintain reading queues and write evidence-based notes;
- move items to Trash with backups and undo where supported.

## Requirements

- Python 3.9+
- `uv` for the shortest install path, or a Python virtual environment with `pip`
- Zotero Desktop 7-9, `zotero-agent`, and the bridge XPI only when doing live Zotero operations

## Beginner Path

There are two separate setup phases:

1. **Install the Agent skill** so Codex can learn the workflow. This does not require Zotero to be open.
2. **Enable live Zotero access** only when you want the Agent to inspect or modify your real library.

Install the companion Codex skill directly from PyPI:

```bash
uvx zotero-librarian skills install --codex
```

Then start a new Codex turn so the newly installed skill is discovered.

Verify the skill-only install without connecting to Zotero:

```bash
uvx zotero-librarian --json doctor --offline
```

For a skill-only install, `skillReady` and `ready` should be `true`. `liveReady`
can remain `false` until `zotero-agent`, the bridge XPI, and Zotero Desktop are
set up.

If `uvx` is not available, use a virtual environment instead:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install zotero-librarian
zotero-librarian skills install --codex
```

For Claude Code, use the same package with the Claude target:

```bash
uvx zotero-librarian skills install --claude
```

Use `--force` when updating an already installed skill:

```bash
uvx zotero-librarian skills install --codex --force
```

## Live Zotero Setup

Live reads and writes require the upstream backend:

Install and verify the backend first:

```bash
uv tool install zotero-agent
zot init
zot ping
```

Download the bridge XPI from the upstream `zotero-agent` release and review its security notes before installation.

After Zotero Desktop is running and `zot ping` passes, run the full diagnostic:

```bash
zotero-librarian --json doctor
```

For live work, `liveReady` and `ready` should both be `true`.

## Persistent CLI Install

If you want the CLI to stay on your PATH, install it as a persistent tool first:

```bash
uv tool install zotero-librarian
zotero-librarian --json doctor --offline
zotero-librarian skills install --codex --force
```

From a cloned repository, install the CLI locally for development:

```bash
git clone https://github.com/HY-LiYihan/zotero-librarian.git
cd zotero-librarian
python3 -m pip install -e .
zotero-librarian --json doctor --offline
```

The PyPI entrypoint is also available for one-off CLI use:

```bash
uvx zotero-librarian --help
```

The legacy installer remains available for users who only want to copy the skill:

```bash
./install.sh --codex
```

## Agent quickstart

```bash
zotero-librarian --json doctor
zotero-librarian --json library export --out library.json
zotero-librarian --json library status library.json --expect-items 229
zotero-librarian --json library audit library.json --strict
```

For identity conflicts:

```bash
zotero-librarian --json identity audit library.json --only-conflicts --workers 4 --output identity.json
zotero-librarian identity report library.json identity.json --output conflicts.md
zotero-librarian identity decision library.json identity.json --expect-items 229 --output decision.md
zotero-librarian --json identity plan library.json identity.json --output source-plan.jsonl --report source-plan.json
zotero-librarian --json plan preview source-plan.jsonl --extended
```

For reviewed writes:

```bash
zotero-librarian --json plan validate edits.jsonl --taxonomy taxonomy.example.toml
zotero-librarian --json plan preview edits.jsonl
zotero-librarian --json plan sample edits.jsonl --out sample.jsonl --count 2
zotero-librarian --json plan apply edits.jsonl --yes
```

`plan apply` runs `zot backup` before applying. Extended creator or item-type repairs use `--extended` and the guarded applier that originated as `librarian_apply.py`.

## Command map

- `doctor`: check package, config, embedded skill, `zot`, and bridge readiness.
- `schema plan|audit|status`: show stable JSON shapes for Agents.
- `skills list|read|install`: inspect and install the embedded companion skill.
- `library export|audit|status`: export the library and run completion gates.
- `identity audit|report|decision|plan`: detect metadata identity conflicts and build guarded repair plans.
- `metadata enrich`: generate abstract or DOI plans without writing to Zotero.
- `plan validate|preview|sample|apply`: validate, dry-run, sample, and apply JSONL changes.
- `item get|pdf|notes`: read exact item metadata, PDF path, or child notes.
- `raw zot -- ...`: escape hatch for direct `zot` commands; known writes require `--allow-write`, and `zot exec` is always refused.

## JSON policy

Use `--json` whenever an Agent will parse output. JSON commands emit JSON to stdout only; diagnostics and subprocess failures go to stderr or into a sanitized error envelope:

```json
{"ok":false,"error":{"code":"confirmation_required","message":"refusing to write without --yes; run plan preview first","details":{}}}
```

Commands never print bridge tokens, Zotero API keys, WebDAV credentials, private env files, live library exports from unrelated paths, or complete private config contents.

## Completion gates

The CLI wraps the same checks previously exposed by `library_audit.py` and `goal_status.py`:

```bash
zotero-librarian --json library status library.json --expect-items <BASELINE>
```

The status report separates:

- `automationComplete`: no remaining actionable missing tags, metadata, PDF queue issues, or parent-count drift.
- `fullComplete`: no documented metadata conflict or manual review item remains.

If `automationComplete` is true but `fullComplete` is false, the Agent must stop for a user identity decision. Use `identity audit`, `identity report`, `identity decision`, and only after user approval `identity plan`. This replaces the direct script sequence around `source_identity_plan.py` while keeping the script available for compatibility.

## Safety boundary

- No Zotero Web API key is required or stored.
- No direct `zotero.sqlite` writes.
- No permanent deletion or Trash emptying.
- No arbitrary JavaScript endpoint is added by this project.
- Batch operations are dry-run first, backed up, sampled when appropriate, verified, and undoable where the backend supports it.
- PDFs are imported locally as Zotero stored attachments; Zotero Desktop applies the user's configured WebDAV or storage policy.
- v1 does not ship an MCP server.

See [SECURITY.md](SECURITY.md) for the trust boundary and reporting process.

## Development

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/zotero-librarian
python3 -m build
```

Smoke-test from another directory before release:

```bash
cd /tmp
zotero-librarian --help
zotero-librarian --json doctor --offline
zotero-librarian --json schema plan
```

Default CI is offline and does not access a live Zotero library. See [docs/live-testing.md](docs/live-testing.md) for disposable-library live test guidance and [docs/release.md](docs/release.md) for the release checklist.

## License and attribution

MIT. This project depends on, but is not affiliated with, `alex-roc/zotero-agent`, which is also MIT licensed. Zotero is a trademark of the Corporation for Digital Scholarship; this project is not affiliated with or endorsed by Zotero.
