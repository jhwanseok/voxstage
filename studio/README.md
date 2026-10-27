# voxstage studio

A management console for the content the engine runs on (FAQ, flows, tools, notices, policy). A reference and
learning implementation built like a product. Design: [docs/studio/](../docs/studio/README.md), ADR
[0012](../docs/decisions/0012-studio-management-console.md) and [0013](../docs/decisions/0013-studio-database-source-of-truth.md).
It never edits `voxstage/`; it only imports it (`DomainPack.load`, `load_flows`) to validate.

A **bot** is one domain in one language (`bank-en`). Publishing a bot writes an engine `domains_dir` to `studio/exports/<bot>/`.

## Run (local, single user, no login)

```bash
docker compose -f studio/docker-compose.yml up -d        # Postgres on localhost:5433

cd studio/backend
python -m venv .venv && .venv/Scripts/python -m pip install -e ../.. -e ".[test]"   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn studio_backend.main:app --port 8000

cd studio/frontend
npm install && npm run dev                                # http://localhost:5173, proxies /api to :8000
```

Open the app, press **Import** on a domain from `domains/`, then edit FAQ and tools, look at the flows, **Validate**,
**Publish**. Point the engine at `studio/exports/<bot>` as its domains directory to run the published content.

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
