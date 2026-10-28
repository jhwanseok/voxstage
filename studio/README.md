# voxstage studio

A management console for the content the engine runs on (FAQ, flows, tools, notices, policy). A reference and
learning implementation built like a product. Design: [docs/studio/](../docs/studio/README.md), ADR
[0012](../docs/decisions/0012-studio-management-console.md) and [0013](../docs/decisions/0013-studio-database-source-of-truth.md).
It never edits `voxstage/`; it only imports it (`DomainPack.load`, `load_flows`) to validate.

A **bot** is one domain in one language (`bank-en`). Publishing a bot writes an engine `domains_dir` to `studio/exports/<bot>/`.

## Run (local, single user, no login)

One command, from the repository root (Docker, Python 3.10+ and Node 20+ needed; the first run creates the venv and
installs packages):

```bash
python studio/dev.py            # Postgres, migrations, seed (imports domains/), backend, frontend; Ctrl+C stops the servers
python studio/dev.py --check    # does the same, probes everything, stops the servers, exits 0 or 1
```

| What | Address |
|---|---|
| Studio (open this) | http://127.0.0.1:5710 |
| Backend API (docs at `/docs`) | http://127.0.0.1:8710/api/v1 |
| Postgres (Docker, user, password and database `studio`) | localhost:5433 |

Ports are fixed and do not clash with 4322, 5173 or 8000. On first start every domain of `domains/` is imported as bots
(`bank-en`, `bank-ko`, ...). Edit FAQ and tools, look at the flows, **Validate**, **Publish**; point the engine at
`studio/exports/<bot>` as its domains directory to run the published content. By hand: see the steps in `dev.py`
(`docker compose up -d`, `alembic upgrade head`, `python -m studio_backend.seed`, `uvicorn`, `npm run dev`).

## Tests

```bash
cd studio/backend && .venv/Scripts/python -m pytest      # needs the Postgres above; builds a throwaway database
cd studio/frontend && npm test && npm run build
```

`tests/test_contract.py` is the contract of ADR 0012/0013: import `domains/`, export every bot, parsed YAML equals the
source, and the engine's loader accepts the export.

## State

ST1 (this version): import, export, loader-based validation, publish and history, FAQ and tools forms, read-only
flow graph with automatic layout. Flow editing, rollback, diff are ST2; notices, settings, policy, preview are ST3.
Configuration by environment: `STUDIO_DATABASE_URL`, `STUDIO_DOMAINS_ROOT`, `STUDIO_EXPORT_ROOT`.
