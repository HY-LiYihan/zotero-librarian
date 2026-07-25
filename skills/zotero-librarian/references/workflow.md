# Library Workflow

## 1. Scope and Audit

Resolve the requested collection, tag, query, or explicit item keys. Prefer narrow scopes.

```bash
zot ping
zot collections --json
zot tags --json
zot lint --json
zot missing abstract --collection <KEY> --json
zot missing doi --collection <KEY> --json
zot dedupe --collection <KEY> --json
```

Use `zot search`, `zot get`, `zot pdf`, `zot annotations`, and `zot notes` for evidence. Do not classify from titles alone when abstracts or PDFs are available.

For a named collection such as Inbox:

1. Run `zot collections --all --json` and resolve an exact collection key. If multiple collections have the same leaf name, show their keys/hierarchy and ask the user to choose. If none exists, report that fact; do not create it during an audit.
2. List the collection without changing Zotero: `zot export <COLLECTION_KEY> --format json`. Do not pass `--out` in a proposal-only audit.
3. Exclude attachments, notes, and annotations from paper counts. Inspect bibliographic parents with `zot get <ITEM_KEY> --json`; use `zot pdf`, `zot annotations`, and `zot notes` only for relevant items.
4. Paginate global lists with `--all`; never infer that the default first page is the whole library.

When the user asks only for an audit or proposal, remain strictly read-only: do not call `zot add`, `zot apply`, `zot backup`, `zot collection`, `zot dedupe --merge`, `zot enrich`, `zot move`, `zot note`, `zot set`, `zot tag`, or `zot exec`; do not create plan or taxonomy files. Return the proposed taxonomy and classifications in the response and state that no Zotero or local files were changed.

## 2. Build a Plan

Write one JSON object per item. Use only the upstream `zot apply` fields:

```json
{"key":"ABCD1234","set":{"abstractNote":"Verified abstract"},"addTags":["topic:robotics","status:to-read"],"removeTags":["To Read"],"addToCollection":"Robotics","trash":false}
```

Validate before preview:

```bash
python3 scripts/librarian_guard.py taxonomy taxonomy.toml
python3 scripts/librarian_guard.py plan edits.jsonl --taxonomy taxonomy.toml
zot apply edits.jsonl --dry-run --json
```

Present impact counts, ambiguous items, and a small representative sample. Do not silently create near-synonym tags or collections.

## 3. Apply and Verify

After explicit approval:

```bash
zot backup
zot apply sample.jsonl --yes --json
zot get <SAMPLE_KEY> --json
zot apply edits.jsonl --yes --json
```

Keep the backup path and operation ID. Re-query affected items and verify exact field, tag, collection, attachment, note, or Trash state. On mismatch, stop and use `zot undo <operation-id>` where supported.

## Special Cases

- Duplicate merge: run exact DOI and title detection before fuzzy detection. For every group, compare DOI/ISBN/arXiv ID, title, creators, year, item type, fields, tags, collections, notes, and attachments. The upstream merge always keeps the oldest item as master and merges every group in the selected scope. Use `zot dedupe --merge` only when the user approves every reported group and accepts the oldest master for each. Otherwise stop and direct the user to merge the selected group in Zotero's Duplicate Items UI; do not use `zot exec` to bypass this limit. Immediately before an approved merge, disable auto-sync, run `zot backup`, re-run the same scoped detection, and confirm the groups are unchanged. After merging, verify the master retains expected metadata, tags, collections, notes, and attachments, then let the user re-enable sync. A merge has no `zot undo`; recovery requires restoring the printed database backup.
- Deletion: set `trash: true`; never erase or empty Trash.
- New collections: preview names and parents, reject case-insensitive duplicates, then create them before applying item membership plans.
- Enrichment: dry-run Crossref/OpenAlex candidates and retain source identifiers. Do not overwrite non-empty conflicting metadata automatically.
- Large jobs: split into reviewable batches and verify each batch before continuing.
