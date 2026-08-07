# Live Zotero Testing

Default CI is intentionally offline. It must not connect to a real Zotero library, inspect private items, or write through the bridge. Use this checklist only with a disposable Zotero profile or test library.

## Setup

1. Create or select a disposable Zotero library.
2. Install `zotero-agent` and its bridge XPI.
3. Run `zot init` and `zot ping`.
4. Install the local package:

```bash
python3 -m pip install -e .
zotero-librarian --json doctor
```

## Read-only checks

```bash
zotero-librarian --json library export --out /tmp/zotero-live-library.json
zotero-librarian --json library audit /tmp/zotero-live-library.json --strict
zotero-librarian --json identity audit /tmp/zotero-live-library.json --only-conflicts --workers 2 --output /tmp/zotero-live-identity.json
```

## Write checks

Run writes only on test items created for the disposable library.

1. Create a one-item JSONL plan that adds and removes harmless namespaced tags.
1. Preview it:

```bash
zotero-librarian --json plan preview /tmp/zotero-live-edits.jsonl
```

1. Apply it only after confirming the target item key belongs to the disposable library:

```bash
zotero-librarian --json plan apply /tmp/zotero-live-edits.jsonl --yes
```

1. Verify the item with `zotero-librarian --json item get <KEY>`.
1. If verification fails, use the printed operation ID with `zot undo <OP_ID>`.

## Forbidden in live tests

- Do not run against the user's main library.
- Do not use `raw zot --allow-write` unless the exact command is already covered by this checklist.
- Do not run `zotero-librarian raw zot -- exec ...`; the CLI refuses this path.
- Do not permanently delete, empty Trash, edit `zotero.sqlite`, or copy files into `Zotero/storage`.
