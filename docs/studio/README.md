# Studio design (all open decisions answered; awaiting approval to build)

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

## Bots (consequence of decision 2)

- A **bot** = one domain in one language (`bank-en`). Bots of a domain are independent for content, validation,
  drafts, publications and history. They share the domain's language-free assets: `tools.yaml`, `sensitive_slots.yaml`,
  `readback_slots.yaml` (this is how the engine already lays them out).
- **Mapping to the engine format:** import of `domains/bank/` creates the domain `bank` (shared assets) and bots
  `bank-en`, `bank-ko`. A bot's publication exports a complete `domains_dir` (`studio/exports/bank-en/bank/...`) that
  holds only that language. The engine already loads one language per pack, so nothing changes in the core.
- **Cross-language references:** the loader has none; the only link between languages is the engine's twin test,
  which is a dataset rule. The studio offers an optional sibling check (warnings, off by default) and "start from a
  sibling" when creating a bot; neither blocks anything.
- **Shared assets:** a change to a tool affects every bot of the domain. Validation of each bot goes stale on a shared
  change and the editor says which bots are affected; published bots are not changed until they are published again.
- **Publish unit (decision 1, changed):** the bot. A domain-wide publish would force a Korean bot to wait for
  the English one.

## Open decisions (recommendation first; asked one at a time)

1. **Publish unit.** DECIDED 2026-10-27: the bot (domain x language). First chosen as "a whole domain, all languages"
   ("도메인전체로하자"); changed after decision 2 because a bot has one language. Owner's words: "응 같은도메인도 언어다르면
   분리해주고, 도메인별로 봇단위를 분리해줘". Same domain with another language is a separate bot (`bank-ko`, `bank-en`);
   another domain is a separate bot.
2. **Language.** DECIDED 2026-10-27 ("봇별로 언어를 설정하게하자"): each bot has one language and its content is edited
   in that language only; no screen edits an English and a Korean flow together. Consequences: see "Bots".
3. **Rollback semantics.** DECIDED 2026-10-27 (as recommended, "추천대로 해줘"): a rollback to publication N creates a new
   publication from N's snapshot and resets the draft to it. History is kept. With unpublished draft changes the
   caller must confirm "discard and proceed" (`discard_draft: true`).
4. **Layout and rollback.** DECIDED 2026-10-27 (as recommended, "응 그렇게하자"): layout is not versioned and not part of a
   publication. Only the current layout is kept; a rollback leaves the positions of surviving nodes as they are, nodes
   that no longer exist lose their position, and nodes without one are placed by Auto layout.
5. **Held-out rule.** DECIDED 2026-10-27 (as recommended, "추천안대로 하자"): the studio does not enforce "patterns are written
   without reading the paraphrases" (ADR 0009); that is a method of the dataset, not of operators. The FAQ form shows
   paraphrases and ASR variants next to the pattern. Datasets are still written as `domains/` files by the engine track.
6. **Frontend test depth.** DECIDED 2026-10-27 (as recommended, "추천안대로 진행해줘"): small component tests (Vitest) for the
   editor rules, plus one end-to-end test (Playwright) of import, edit, validate, publish, rollback.
