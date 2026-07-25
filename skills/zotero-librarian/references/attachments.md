# Attachment Policy

## Default

Import PDFs as Zotero stored attachments through the running desktop bridge. Zotero Desktop then applies its configured Zotero Storage or WebDAV synchronization policy. Local bridge imports do not upload bytes through the Zotero Web API.

## Linked Files

Use linked files only when the user explicitly provides a stable absolute root that exists on every required machine or is managed by their own sync tool. Validate the file exists before linking.

## Repair and Acquisition

- Inspect current children before adding another PDF.
- Prefer a verified open-access publisher, DOI, or arXiv source.
- Validate HTTP status, PDF signature, and a reasonable file size.
- Never bypass paywalls, authentication, robots controls, or access restrictions.
- Preserve existing valid attachments; flag probable duplicates for review.

Do not copy files directly into `Zotero/storage`, mutate attachment link modes in place, or call Zotero Web API file-upload endpoints.
