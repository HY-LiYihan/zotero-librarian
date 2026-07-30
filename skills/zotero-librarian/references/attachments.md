# Attachment Policy

## Default

Import PDFs as Zotero stored attachments through the running desktop bridge. Zotero Desktop then applies its configured Zotero Storage or WebDAV synchronization policy. Local bridge imports do not upload bytes through the Zotero Web API.

## Linked Files

Use linked files only when the user explicitly provides a stable absolute root that exists on every required machine or is managed by their own sync tool. Validate the file exists before linking.

## Repair and Acquisition

- Do not run `zot missing pdf`: `pdf` is not a supported `zot missing` field and
  current CLI versions report every parent item as missing. Use `zot stats` for
  aggregate counts and inspect each item's `links.attachment` or `zot pdf KEY`
  for authoritative attachment state.
- Inspect current children before adding another PDF.
- Current `zot` versions do not expose a safe command to attach a PDF to an
  existing parent item. Do not use `zot add --pdf` as a repair path because it
  creates a new parent item and changes the library's literature count.
- Prefer a verified open-access publisher, DOI, or arXiv source.
- Validate HTTP status, PDF signature, and a reasonable file size.
- Never bypass paywalls, authentication, robots controls, or access restrictions.
- Preserve existing valid attachments; flag probable duplicates for review.

Do not copy files directly into `Zotero/storage`, mutate attachment link modes in place, or call Zotero Web API file-upload endpoints.
