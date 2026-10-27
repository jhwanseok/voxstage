# Spec ST1: studio foundation, import / export, FAQ and tools forms, flow viewer

Read first: this file, [docs/studio/README.md](../../studio/README.md) and the four documents it lists, ADR 0012 and 0013.
Do not edit `voxstage/` (the engine core). Work on branch `wip/studio-st1`.

## Build order

1. **Skeleton.** `studio/backend` (Python package `studio`, FastAPI, SQLAlchemy 2, Alembic, pytest; `voxstage`
   installed editable and only imported), `studio/frontend` (Vite, React, TypeScript, `@xyflow/react`, dagre, Vitest),
   `studio/docker-compose.yml` (Postgres), `.gitignore` for exports and node_modules. Alembic baseline migration for
   the tables of `data-model.md` that ST1 needs (domain, bot, faq_entry, tool, flow, flow_layout, flow_node_layout,
   domain_setting, domain_file, publication, publication_file, user, role, user_role).
2. **Import.** `POST /domains/import` for `repo_domains`: domain, one bot per language directory, FAQ with patterns
   merged into one row, tools, flows (header, nodes, node_order), shared and per-bot settings, everything else raw.
3. **Export and validate.** Exporter per bot (fixed key order, `studio/exports/<bot>/` as a `domains_dir`),
   `POST /bots/{b}/validate` through the engine loader with the `ValidationReport` shape, `POST publications`
   (publish with note, snapshot, directory swap). History list.
4. **Contract test** (backend, against real Postgres): import `domains/`, export every bot, assert parsed YAML equals the
   source for every modelled and raw file, and that `DomainPack.load` and `load_flows` accept the export for every
   domain and language.
5. **FAQ and tools** endpoints and forms (FAQ entry with pattern and paraphrases shown next to it; tool form).
6. **Flow viewer:** flow list, read-only React Flow graph with the node kinds and edge labels of `screens.md`, dagre
   automatic layout saved to the layout tables, properties panel (read-only), validation items.

After each numbered item: run the backend tests, `npm run build` and `npm test`, run the engine's
`python -m unittest discover -s tests` (it must stay green), commit to `wip/studio-st1`, push.

## Done when

- Import of `domains/` (bank, shop, telecom, both languages) gives 3 domains and 6 bots; the contract test passes.
- A published bot can be loaded by the engine (`DomainPack.load` on `studio/exports/<bot>`).
- FAQ entry and tool edits can be made in the UI, saved, validated and published; validation errors from the loader
  are shown with their file and node.
- Every existing flow is shown as a graph with all node kinds and edge labels, laid out automatically.
- `voxstage/` has zero diff against `dev`.

## Not in ST1

Flow editing, notices and wording forms, settings forms, rollback, diff, sibling check, preview, Playwright test (ST2).
