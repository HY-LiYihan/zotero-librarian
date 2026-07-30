---
name: zotero-librarian
description: Safely audit, organize, classify, read, and maintain a running Zotero Desktop library using the local zot CLI and bridge plugin. Use when an agent needs to design or enforce a collection/tag taxonomy, triage an inbox, maintain reading queues, find duplicates or missing metadata/PDFs, import papers, summarize PDFs into Zotero notes, batch-edit references, or move items to Trash with dry-run, backup, verification, and undo safeguards.
---

# Zotero Librarian

Treat the user's Zotero library as durable research data. Use `zot` and the bundled Librarian scripts for Zotero access; do not use the Zotero Web API, edit `zotero.sqlite`, execute arbitrary JavaScript, or invent a second storage path.

## Start Safely

1. Run `zot ping`. Stop if the local API or bridge is unavailable; read [setup.md](references/setup.md).
2. For organization work, read [workflow.md](references/workflow.md) and the user's taxonomy. If none exists, read [taxonomy.md](references/taxonomy.md), audit the existing library, and propose one before writing.
3. Prefer `zot ... --json` for machine-readable reads. Reuse existing item keys, tags, and collection names exactly.
4. Never print tokens, config files, or private environment files.

## Choose the Workflow

- Audit, classify, tag, move, deduplicate, enrich, or delete: follow [workflow.md](references/workflow.md).
- Create or validate a taxonomy or JSONL edit plan: follow [taxonomy.md](references/taxonomy.md) and run `scripts/librarian_guard.py`.
- Read a PDF, summarize it, or save a child note: follow [pdf-and-notes.md](references/pdf-and-notes.md).
- Import or repair attachments: follow [attachments.md](references/attachments.md).

## Non-Negotiable Safety Rules

- Keep reads local and writes inside the running Zotero process through the `zotero-agent` bridge.
- Default every batch change to preview. Use `zot apply PLAN.jsonl --dry-run`, inspect counts and samples, then obtain user authorization before applying.
- Run `zot backup` before bulk edits, merges, attachment maintenance, or deletion. Test on one or two items and verify in Zotero before the full batch.
- Prefer undoable `zot apply` operations and retain the operation ID. Use `zot undo <operation-id>` when verification fails.
- Delete by setting `trash: true`. Never permanently erase items, empty Trash, execute arbitrary JavaScript, or modify SQLite under this skill.
- Treat duplicate detection as evidence, not permission to merge. Merges require explicit user approval because they are not undoable.
- Import PDFs as Zotero stored attachments so Zotero Desktop applies its configured WebDAV policy. Use linked files only when the user explicitly supplies a stable shared root.
- Never upload attachment bytes through the Zotero Web API.

## Report Results

Report the inspected scope, proposed/applied counts, backup path, operation ID, verification result, and unresolved review items. Do not dump full-library JSON into chat.
