# Zotero Librarian Agent Instructions

Use `skills/zotero-librarian/SKILL.md` for Zotero library-management requests. Treat it as the canonical workflow source; do not duplicate or weaken its safety rules in client-specific instructions.

Before a live operation, run `zot ping`. Reads may proceed after a successful check. Batch or destructive writes require dry-run, user review, backup, sample verification, and explicit authorization. Move items to Trash only; never permanently erase, empty Trash, modify `zotero.sqlite`, print credentials, or upload PDFs through the Zotero Web API.
