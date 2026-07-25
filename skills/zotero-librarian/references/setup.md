# Setup and Diagnostics

## Requirements

- Zotero Desktop 7-9 is running with local API access enabled.
- `zotero-agent` is installed from <https://github.com/alex-roc/zotero-agent>.
- The matching bridge XPI is installed in Zotero.
- `zot init` has created the local mode-600 token configuration.

## Install

```bash
uv tool install zotero-agent
zot init
zot ping
```

Install the bridge XPI from the upstream release before `zot init`. Do not place bridge tokens in Codex `config.toml`, repository files, or prompts.

## Diagnostic Contract

`zot ping` must confirm the local read API, bridge execution, user ID, and CLI version. If it fails:

- Zotero unavailable: start Zotero and confirm local API access is enabled.
- Bridge unavailable: install or enable the XPI; do not fall back to database writes.
- Token failure: rerun `zot init` or rotate the upstream token; do not expose it.
- Unsupported CLI: upgrade `zotero-agent` and retry.

Do not use Web API credentials as a fallback. Metadata writes through the bridge are local, and stored attachments are synchronized by Zotero Desktop using the user's configured storage provider.
