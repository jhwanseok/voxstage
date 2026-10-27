# Studio data model

Decisions: [0012](../decisions/0012-studio-management-console.md), [0013](../decisions/0013-studio-database-source-of-truth.md).
Postgres, SQLAlchemy, Alembic. `jsonb` columns hold content in the same shape as the engine's YAML (parsed), so the
exporter is a dump and the importer is a load. Primary keys are `uuid` unless noted. Every content row has
`created_at`, `updated_at`, `updated_by` (user id) and `revision` (integer, +1 per save, used for optimistic
concurrency). Layout rows are the exception (see below).

## What is stored where

The engine reads, per domain `D` and language `L` (`voxstage/domain_pack.py`, `voxstage/dataset.py`, `voxstage/rules/flows.py`):

| Engine file | Scope | Studio entity | Modelled in |
|---|---|---|---|
| `D/tools.yaml` | domain | `tool` | ST1 (form) |
| `D/sensitive_slots.yaml`, `D/readback_slots.yaml` | domain | `domain_setting` (kind) | ST1 raw, ST3 form |
| `D/L/faq.yaml` | language | `faq_entry` | ST1 (form) |
| `D/L/rules/faq_patterns.yaml` | language | `faq_entry.pattern` (same row as the FAQ entry) | ST1 (form) |
| `D/L/flows/<id>.yaml` | language | `flow` | ST1 view, ST2 edit |
| `D/L/notices.yaml` (`notices`, `wording`) | language | `notice`, `wording` | ST3 (form) |
| `D/L/rules/config.yaml`, `confirm.yaml`, `commands.yaml`, `corrections.yaml`, `confusions.yaml` | language | `domain_setting` (kind) | ST1 raw, ST3 form |
| `D/L/faq_unanswerable.yaml`, `D/L/scenarios/*.yaml` | language | `domain_file` (raw) | raw until a later step |
| policy values (R14) | to be decided by the engine track | `domain_file` (raw) | ST3 after R14 is merged |

A FAQ entry holds its patterns in the same row because the loader refuses a pack in which a FAQ entry has no pattern
(`load_patterns`: "no pattern for FAQ entries"). A form that edited only `faq.yaml` could never produce a valid pack.

**Raw files** (`domain_file`) are the safety net: anything not modelled yet is stored byte-for-byte as text and exported
unchanged, so every publication is a complete pack and new engine features do not block the studio.

## Tables

### Identity and access (slots, not enforced in v1)

| Table | Columns |
|---|---|
| `user` | id, email (unique), display_name, is_active |
| `role` | name (pk): `editor`, `publisher`, `admin` |
| `user_role` | user_id, role_name |

v1 seeds one local user (`local@studio`) with all roles and the API treats every request as that user. The
write endpoints already record `updated_by` and the publish endpoint already checks the `publisher` role through one
dependency (`require_role`), which allows everything in v1. Adding login later changes that dependency only.

### Domain and languages

| Table | Columns |
|---|---|
| `domain` | id, slug (unique, the directory name: `bank`), title, languages (jsonb list, e.g. `["en","ko"]`), draft_revision (+1 on any content change in the domain), last_validated_revision, last_published_number |

### Content (draft)

All content rows reference `domain_id`; language-scoped ones also have `lang`.

| Table | Key | Columns |
|---|---|---|
| `faq_entry` | (domain_id, lang, entry_id) | position (int), question, answer, paraphrases (jsonb list), asr_variants (jsonb list), pattern (jsonb: `all_of`, `any_of`, `none_of`, `priority`, `regex`, `note`, as in `parse_pattern`) |
| `tool` | (domain_id, name) | position, body (jsonb: `params`, `rules`, `default`, `risky`, `requires`, `verifies`, `retry`, as `tools._validate_spec`) |
| `flow` | (domain_id, lang, flow_id) | header (jsonb: `triggers`, `buttons`, `captures`, `interrupts`, `carry`, `prefill`, `role`, `verification`), start (text), nodes (jsonb map node_id to node body), node_order (jsonb list of node ids) |
| `notice` | (domain_id, lang, notice_id) | priority, text, applies_when (nullable). `fixed` is always true |
| `wording` | (domain_id, lang, key) | text. Keys are the fixed set in `domain_pack.WORDING_KEYS` |
| `domain_setting` | (domain_id, lang or null, kind) | body (jsonb). Kinds: `sensitive_slots`, `readback_slots`, `config`, `confirm`, `commands`, `corrections`, `confusions` |
| `domain_file` | (domain_id, path) | content (text), content_type. Path relative to the domain directory |

`flow.nodes` keeps each node exactly as the YAML mapping (`{type: ask, slot: ..., next: ...}`), so the loader's key
checks apply unchanged. The flow id is the file name; the `id` key inside the file is generated from it on export.
`node_order` fixes the order in which nodes are written, because `jsonb` does not keep key order.

### Layout (kept apart from meaning)

| Table | Key | Columns |
|---|---|---|
| `flow_layout` | (domain_id, lang, flow_id) | viewport (jsonb: x, y, zoom), direction (`LR` or `TB`), saved_at, saved_by |
| `flow_node_layout` | (domain_id, lang, flow_id, node_id) | x, y (floats), collapsed (bool) |

- Layout rows do not take part in `revision`, `draft_revision` or validation. Moving a node never makes the draft
  "changed" and never appears in a publication or its diff.
- A layout row for a node that no longer exists is deleted on the next flow save. A node without a layout row is
  placed by the automatic layout on load.
- Layout is not exported. It is not in a publication either: a rollback restores meaning, and positions of
  surviving nodes stay as they are (open decision 4).

### Publications

| Table | Columns |
|---|---|
| `publication` | id, domain_id, number (int, unique per domain, starts at 1), note, published_by, published_at, kind (`publish` or `rollback`), restored_from_number (nullable), content_hash (hash of all files in path order), validation (jsonb: report at publish time, warnings only) |
| `publication_file` | publication_id, path, content (text) |

- A publication is immutable. `publication_file` holds exactly what was written for the engine.
- The export directory `studio/exports/<domain>/` always equals the newest publication. It is written to a temporary
  directory next to it and renamed, so the engine never reads half a pack.
- Rollback to number N: copy N's files into a new publication (kind `rollback`), then load them into the draft with the
  importer (replacing meaning rows, keeping layout of surviving nodes). Draft edits made after N are replaced; the
  endpoint refuses when the draft has unpublished changes unless `discard_draft: true` is sent.

### Validation results

Not stored per edit. `POST validate` returns a report (below); the last result is cached in memory by
`(domain_id, draft_revision)`. `domain.last_validated_revision` says whether the draft was valid at its current
revision, which is what the Publish button needs.

```
ValidationReport {
  draft_revision: int, ok: bool,
  items: [{ severity: "error"|"warning", source: "engine"|"studio", code: str,
            file: str, lang: str|null, flow_id: str|null, node_id: str|null, field: str|null, message: str }]
}
```

`engine` items come from the loader's exceptions (`RuleError`, `FlowError`, `ValueError`, the dataset errors). The
message names the file and often the node; the studio extracts `flow_id`, `lang` from the file path and `node_id`
from the `node <id>` text and keeps the full message as is. Items the studio cannot place point at the file. `studio`
items are checks the loader does not make (see screens: twin check).

## Export rules (the only code that writes the engine format)

1. Write each language directory and `tools.yaml` from rows in `position` order; flows in `node_order`.
2. Fixed key order per file, UTF-8, block style, no comments, `allow_unicode`.
3. Generated pieces: the `lang` key in `faq.yaml`, the `id` key in flow files, `fixed: true` in notices,
   `entries:` wrappers.
4. Raw files and `domain_setting` rows are written as is.
5. Validation is: export to a temporary directory, then `DomainPack.load(tmp, domain, lang)` for each language and
   `load_flows(...)` for the flows, as `interpreter.py` does.

## Import rules

Read the tree with plain `yaml.safe_load` (not the loader, so an invalid pack can still be imported and
fixed), fill the tables, store unknown files raw. Re-import of an existing domain is refused unless `replace: true`
(it replaces the draft only; publications stay). The contract test is: import `domains/`, export, parse both
sides, assert equal; run the loader on the export.

## Indexes and constraints

Unique keys as in the tables; foreign keys with `on delete cascade` from content to `domain`; `faq_entry.entry_id`
unique per (domain, lang); check `revision >= 1`. GIN indexes are not needed (no content search in v1).
