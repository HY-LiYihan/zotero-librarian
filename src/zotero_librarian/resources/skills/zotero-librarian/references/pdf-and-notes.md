# PDF Reading and Notes

1. Resolve the item and local PDF with `zotero-librarian --json item get <KEY>` and `zotero-librarian --json item pdf <KEY>`.
2. Read the local file with the Agent's PDF tool. For long works, summarize section to chapter to whole document.
3. Include page references for claims and distinguish paper claims from Agent interpretation.
4. Read existing annotations with `zot annotations <KEY> --json`; treat them as user interest signals. Use raw `zot` only because the v1 CLI does not wrap annotations yet.
5. Prepare an HTML child note and preview with `zot note <KEY> --file NOTE.html --dry-run`.
6. After approval, save with `zot note <KEY> --file NOTE.html --if-not-exists --yes` and verify with `zotero-librarian --json item notes <KEY>`.

Do not fabricate page numbers, rewrite existing notes without approval, or create PDF annotations through guessed coordinates.
