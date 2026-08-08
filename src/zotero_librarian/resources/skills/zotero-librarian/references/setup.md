# Setup and Diagnostics

## Requirements

- Zotero Desktop 7-9 is running with local API access enabled.
- `zotero-agent` is installed from <https://github.com/alex-roc/zotero-agent>.
- The matching bridge XPI is installed in Zotero.
- `zot init` has created the local mode-600 token configuration.

## Live Setup Order

Follow this order for live Zotero access:

1. Install `zotero-agent`.
2. Install the matching bridge XPI from the upstream `zotero-agent` release.
3. Start Zotero Desktop and confirm local API access is enabled.
4. Run `zot init` to create the local mode-600 token configuration.
5. Run `zot ping` to verify the local API, bridge execution, user ID, CLI
   version, and bridge version.
6. Run `zotero-librarian --json doctor`.

## Install Commands

```bash
uv tool install zotero-agent
zot init
zot ping
```

Use `uv tool upgrade zotero-agent` for upgrades. If `zot ping` reports that the
bridge plugin is older than the CLI, update the XPI from the same upstream
release before performing writes. Remove or repoint stale `zot` shims when
`command -v zot` and `zot --version` differ between Agent shells.

Install the bridge XPI from the upstream release before `zot init`. Do not place bridge tokens in Codex `config.toml`, repository files, or prompts.

After installing only the Agent skill, verify the skill-only path without live
Zotero access:

```bash
zotero-librarian --json doctor --offline
```

`skillReady: true` means the Agent workflow is installed. `liveReady: false` is
expected until `zotero-agent`, the bridge XPI, and Zotero Desktop are ready.

After `zot ping` succeeds with Zotero Desktop running, verify live access:

```bash
zotero-librarian --json doctor
```

## Diagnostic Contract

`zot ping` must confirm the local read API, bridge execution, user ID, CLI
version, and a compatible bridge version. If it fails:

- Zotero unavailable: start Zotero and confirm local API access is enabled.
- Bridge unavailable: install or enable the XPI; do not fall back to database writes.
- Token failure: rerun `zot init` or rotate the upstream token; do not expose it.
- Unsupported CLI: upgrade `zotero-agent` and retry.

Do not use a Zotero Web API key or Web API credentials as a fallback. Metadata
writes through the bridge are local, and stored attachments are synchronized by
Zotero Desktop using the user's configured storage provider.
