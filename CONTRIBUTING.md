# Contributing

Keep this project focused on high-level, safety-first library workflows. Changes that reimplement the Zotero bridge, add Web API file uploads, expose arbitrary JavaScript, permanently erase items, or directly modify SQLite are out of scope.

## Development

1. Create a branch from `main`.
2. Keep `SKILL.md` concise and move task-specific detail into one-level references.
3. Add standard-library tests for deterministic scripts.
4. Run `python3 -m unittest discover -s tests -v`.
5. Run the OpenAI skill creator `quick_validate.py` against `skills/zotero-librarian`.
6. Test live changes only against a disposable Zotero library and describe the test scope in the pull request.

Do not include credentials, absolute home-directory paths, personal taxonomy values, live library exports, PDFs, or Zotero backups in fixtures.
