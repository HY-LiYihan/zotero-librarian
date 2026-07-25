# Zotero Librarian

Zotero Librarian is a safety-first workflow skill for agents that organize and maintain a local Zotero library. It adds taxonomy design, library audits, reviewable JSONL change plans, PDF-reading workflows, and explicit backup/undo rules on top of [`zotero-agent`](https://github.com/alex-roc/zotero-agent).

[简体中文](README.zh-CN.md)

## Why this project

`zotero-agent` already provides the hard part: fast local reads and authenticated writes inside a running Zotero process. Zotero Librarian deliberately does not replace that bridge. It tells an Agent how to turn those primitives into a controlled library-maintenance process:

- audit collections, tags, metadata, duplicates, and attachments;
- classify papers with a user-owned taxonomy;
- preview and validate batch edits before applying them;
- maintain reading queues and write evidence-based notes;
- import stored attachments for Zotero Desktop/WebDAV synchronization;
- move items to Trash, with backups and undo where supported.

## Requirements

- Zotero Desktop 7-9, running locally
- Python 3.9+
- [`zotero-agent`](https://github.com/alex-roc/zotero-agent) CLI and bridge XPI
- `tomli` only when running the plan guard on Python 3.9-3.10

Install and verify the backend first:

```bash
uv tool install zotero-agent
zot init
zot ping
```

Download the bridge XPI from the upstream `zotero-agent` release. Review its security documentation before installation.

## Install the skill

```bash
git clone https://github.com/HY-LiYihan/zotero-librarian.git
cd zotero-librarian
./install.sh --codex
```

For Claude Code use `./install.sh --claude`. Pass both flags to install for both clients. The canonical skill remains in `skills/zotero-librarian/`.

## Use

Invoke `$zotero-librarian` and describe the desired outcome, for example:

- "Audit my Inbox and propose a taxonomy without changing the library."
- "Classify this collection using my taxonomy, preview the plan, then wait."
- "Find duplicate papers and show merge evidence."
- "Summarize this PDF with page references and draft a Zotero child note."
- "Move these exact item keys to Trash after backup and dry-run."

Validate the included examples:

```bash
python3 skills/zotero-librarian/scripts/librarian_guard.py taxonomy taxonomy.example.toml
python3 skills/zotero-librarian/scripts/librarian_guard.py plan \
  examples/edits.example.jsonl --taxonomy taxonomy.example.toml
```

The guard validates policy and shape only. Scientific classification remains the Agent's responsibility and must be grounded in item metadata or PDF evidence.

## Safety boundary

- No Zotero Web API key is required or stored.
- No direct `zotero.sqlite` writes.
- No permanent deletion or Trash emptying.
- No arbitrary JavaScript endpoint is added by this project.
- Batch operations are dry-run first, backed up, sampled, verified, and undoable where the backend supports it.
- PDFs are imported locally as Zotero stored attachments; Zotero Desktop applies the user's configured WebDAV or storage policy.

See [SECURITY.md](SECURITY.md) for the trust boundary and reporting process.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/zotero-librarian
```

The test suite does not access a live Zotero library. Live forward tests must use a disposable test library.

## License and attribution

MIT. This project depends on, but is not affiliated with, `alex-roc/zotero-agent`, which is also MIT licensed. Zotero is a trademark of the Corporation for Digital Scholarship; this project is not affiliated with or endorsed by Zotero.
