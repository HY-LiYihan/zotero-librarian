# Security Policy

## Trust boundary

Zotero Librarian contains Agent instructions and an offline plan validator. It does not expose a network service and does not write to Zotero itself. Local Zotero writes are delegated to the separately installed `zotero-agent` bridge, whose token, loopback, audit, and arbitrary-JavaScript security model must be reviewed independently.

Do not commit or print bridge tokens, Zotero API keys, WebDAV credentials, private environment files, live library exports, or backups. The repository and skill must never require a Zotero Web API key.

## Safe operation

- Use a disposable Zotero test library for live integration tests.
- Back up before bulk writes and retain the operation ID for undo.
- Treat merge as irreversible and require explicit approval.
- Move items to Trash; never permanently erase or empty Trash.
- Never modify `zotero.sqlite` or write directly into `Zotero/storage`.
- Obtain the bridge XPI only from the upstream project release.

## Reporting

Report suspected vulnerabilities privately to `liyihan.xyz@gmail.com`. Do not include real credentials or private library contents in the report. Supported security fixes target the latest release.
