# 0013. Studio: the database is the source of truth; publishing exports the YAML the engine loads

Status: accepted
Date: 2026-10-27
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

The engine loads YAML from `domains/<domain>/...` (ADR 0003). The studio needs drafts, publish history, rollback and
data that is not part of the meaning of a flow (node positions). Files in git give history, but not a draft that is
not valid yet: a half-finished flow cannot be saved as a file the loader accepts.

## Options considered

1. Files are the source of truth; the studio edits them in place.
2. The database is the source of truth; publishing writes the YAML the engine loads. Import goes the other way, once.
3. The database is the source of truth and the engine reads the database directly.

## Decision

We will build option 2, and keep option 3 possible for later.

- Postgres holds the draft content, the publication history and the layout. Meaning (what the engine reads) and
  layout (node x, y, viewport) are stored in separate tables; layout is never exported.
- **Publishing** validates the draft with the engine's own loader on a temporary export. Only if it passes, an
  immutable snapshot (the exported files) is stored as a numbered publication and written to the export directory
  that the engine is pointed at as its domains directory.
- **Import** reads an existing `domains/<domain>/` tree into the draft. Files the studio does not model yet (for example
  `rules/*.yaml`, scenarios) are stored as raw files and exported unchanged, so a publication is always a complete
  domain pack.
- Round trip means *parsed equality*, not byte equality: comments and key order of the source YAML are not kept. The
  exporter writes a fixed key order.
- Rolling back creates a new publication from an old snapshot; history is never rewritten.
- Content is organised in **bots**: one domain in one language (`bank-en`). A bot has its own draft, validation and
  publications; language-free assets (`tools.yaml`, slot lists) belong to the domain and are exported with every bot.
  The unit of validation and publication is the bot (the owner first chose the whole domain, then one language per bot,
  and confirmed the bot as the unit on 2026-10-27). The loader has no cross-language references; the English /
  Korean twin rule is an engine test, and the studio reports it only as an optional warning.

## Rationale

- A draft the loader rejects can still be saved: the database does not run the loader on write, only on validate and
  publish.
- Snapshots stored as exported files, not as rows, mean a publication is exactly what the engine loaded; there is no
  second code path that can drift.
- Option 3 would put a database driver into the engine and move validation from file load to DB load; that is a core
  change and belongs to the engine track. Option 2 does not close that door: the same snapshots can be read through
  an adapter later.
- `jsonb` for flow bodies and other nested content: the content is nested, changes shape with the engine's steps, and
  is validated by the engine, not by the schema. `jsonb` keeps neither key order nor duplicate keys, so ordered things
  (node order, branch cases, FAQ order) are stored as lists or position columns.

## Public basis

- [Dialogflow CX versions](https://docs.cloud.google.com/dialogflow/cx/docs/concept/version) (read 2026-10-27): draft,
  immutable versions, rollback to an earlier version, a version can be loaded back into the draft.
- [PostgreSQL: JSON types](https://www.postgresql.org/docs/current/datatype-json.html) (read 2026-10-27): `jsonb` is
  recommended for most applications; it does not preserve key order or duplicate keys.
- [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html) (read 2026-10-27): versioned migration
  scripts with upgrade and downgrade.
- Own experiment: the ST1 contract test (import, export, load, compare parsed content).

## Consequences

- Two representations of the content exist (DB rows and exported files). The exporter is the only code that writes the
  engine's format, and it is tested against the real `domains/`.
- Anything the engine track adds to the YAML format (R14 policy) works in the studio at once as a raw file, and gets a
  form later.
- Hand edits to files in `domains/` are not seen by the studio until re-imported. `domains/` stays the engine
  track's dataset; the studio exports to its own directory (`studio/exports/`, git-ignored).
- Comparing two publications is a diff of exported files.

## Open questions

See [docs/studio/README.md](../studio/README.md), "Open decisions".

## Decider's note

"도메인전체로하자" (publish unit: a whole domain, all languages; 2026-10-27), then "봇별로 언어를 설정하게하자" (a language per bot; 2026-10-27), and finally "응 같은도메인도 언어다르면 분리해주고, 도메인별로 봇단위를 분리해줘" (a bot is domain x language and is the publish unit; 2026-10-27).
