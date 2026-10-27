# Studio design (proposed, awaiting approval)

A management console for the content the engine runs on: FAQ, flows, tools, notices, policy. A reference and
learning implementation built like a product. Nothing here is built until the owner approves it.

| Document | Content |
|---|---|
| [ADR 0012](../decisions/0012-studio-management-console.md) | Why a console, in this repository, outside the engine core |
| [ADR 0013](../decisions/0013-studio-database-source-of-truth.md) | Database as source of truth, publish exports the YAML |
| [data-model.md](data-model.md) | Tables, layout apart from meaning, publications, export and import rules |
| [api.md](api.md) | Endpoints, validate / publish / import / rollback flows |
| [screens.md](screens.md) | Screens, the flow node-graph editor, validation display, auto layout |

## Layout of the code (when built)

```
studio/
  backend/    FastAPI, SQLAlchemy, Alembic, pytest; installs voxstage editable (read-only use)
  frontend/   React, TypeScript, Vite, @xyflow/react, dagre
  exports/    publish output, git-ignored
  docker-compose.yml   Postgres for local use
```

## Boundary with the engine track

- The studio imports `voxstage` and calls `DomainPack.load`, `load_flows`, `evaluate`; it never edits `voxstage/`.
- It reads `domains/` only through the importer; it writes only to `studio/exports/`.
- Contract test (ST1): import `domains/` -> export -> parsed equality with the source, and the exported tree loads.
  It runs in the studio's test suite, not the engine's, and fails when the engine changes the format in a way the
  studio does not model (unmodelled files are carried raw, so most additions pass).
- Possible engine-track items, only if the studio proves it needs them: structured loader errors (file, node, field
  as attributes instead of message text); a `domains_dir` argument wherever the engine still assumes `domains/`.

## Run-queue track

Studio items ST1 to ST3 are in [queue.md](../plan/queue.md), section "Studio track". First range:

1. **ST1** Foundation, import / export, FAQ and tools forms, flow viewer, validation through the loader.
2. **ST2** Flow editing, layout storage, validation display, publish, history, diff, rollback.
3. **ST3** Notices and wording, settings, policy (after R14 is merged), preview chat.

## Open decisions (recommendation first; asked one at a time)

1. **Publish unit.** DECIDED 2026-10-27 (as recommended, "도메인전체로하자"): a whole domain, all languages. The loader
   checks references across files and the EN/KO twin rule spans languages.
2. **Twin flows.** Edit English and Korean flows separately with a twin check, or one shared structure with per-language
   text. Recommended: separate files with a check (the engine's format is two files; shared structure is a
   later feature).
3. **Rollback semantics.** Rollback makes a new publication and resets the draft (recommended), or only loads the old
   snapshot into the draft for the owner to publish after review.
4. **Layout and rollback.** Layout is not versioned; positions of surviving nodes stay (recommended), or layout is
   snapshotted with each publication.
5. **Backend validation of the held-out rule.** The FAQ pattern rule "patterns are written without reading the
   paraphrases" (ADR 0009) is a method of the dataset, not of operators. Recommended: the studio shows paraphrases next
   to patterns and does not enforce it.
6. **Frontend test depth.** Component tests (Vitest) plus one end-to-end test of import, edit, publish (Playwright),
   or unit tests only. Recommended: both, small.
