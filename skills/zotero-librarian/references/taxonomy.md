# Taxonomy and Plan Rules

Copy [taxonomy.example.toml](taxonomy.example.toml) to a user-controlled location. The taxonomy is policy, not a dump of every Zotero tag.

## Design Rules

- Use collections for stable subject or project membership.
- Use namespaced tags for changing state, priority, method, or workflow.
- Keep `status:*` and `priority:*` mutually exclusive.
- Reuse existing names exactly; propose migrations for spelling/case variants.
- Keep personal domain examples out of the distributed template.
- Do not create collections or tags when the taxonomy forbids them.

## Validation

```bash
python3 scripts/librarian_guard.py taxonomy taxonomy.toml
python3 scripts/librarian_guard.py plan edits.jsonl --taxonomy taxonomy.toml
```

The plan validator rejects unknown fields, malformed item keys, non-namespaced tags when disabled, conflicting exclusive tags, non-boolean Trash values, and permanent-delete vocabulary.

Validation cannot decide whether a classification is scientifically correct. The Agent must cite title/abstract/PDF evidence and leave uncertain items in the configured review collection.
