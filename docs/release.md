# Release Checklist

This project is release-ready but does not publish to PyPI automatically.

## Preflight

```bash
git status --short
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/zotero-librarian
zotero-librarian --json doctor --offline
zotero-librarian --json schema plan
```

## Build

```bash
rm -rf dist build *.egg-info
python3 -m pip install build
python3 -m build
```

Verify from a clean directory:

```bash
tmpdir=$(mktemp -d)
python3 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install dist/*.whl
cd /tmp
"$tmpdir/venv/bin/zotero-librarian" --help
"$tmpdir/venv/bin/zotero-librarian" --json doctor --offline
"$tmpdir/venv/bin/zotero-librarian" skills read zotero-librarian >/tmp/zotero-librarian-skill.md
```

## Publish gates

- Confirm the PyPI project name is still available.
- Confirm `README.md`, `README.zh-CN.md`, `SECURITY.md`, and `LICENSE` are current.
- Confirm no live library exports, backups, credentials, private env files, or local paths are staged.
- Run `gitleaks detect` or the GitHub Actions secret scan.
- Tag the release only after CI passes on `main`.

## Optional publish commands

Use TestPyPI before production PyPI:

```bash
python3 -m pip install twine
python3 -m twine upload --repository testpypi dist/*
python3 -m twine upload dist/*
```

Do not publish with credentials in shell history or repository files.
