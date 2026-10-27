# 0012. Studio: a management console in the same repository, outside the engine core

Status: proposed
Date: 2026-10-27
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

Everything the engine knows about a domain is data: FAQ entries, FAQ word-group patterns, flows, tools,
notices, policy values (ADR 0003, 0010; "Domains are data" in the project principles). Today that data is edited as
YAML files by hand. A voicebot in production is run by operators who do not edit YAML, and a flow with eight to
fifteen nodes and explicit `next` links is hard to review as text. This repository is a reference implementation of
Voice AI (AICC); a reference that shows how to build the engine but not how to operate it leaves out half of the
job. The decider wants a management console ("studio") built like a real product, used for learning and as a
portfolio of the operating side, alongside the engine.

## Options considered

1. No console: keep editing YAML by hand and rely on the loader's errors.
2. A console in a separate repository.
3. A console in this repository under `studio/`, split into `studio/backend` and `studio/frontend`, with the
   engine core untouched.
4. A console inside the `voxstage/` package.

## Decision

We will build option 3.

- `studio/backend`: FastAPI, SQLAlchemy, Alembic, Postgres. `studio/frontend`: React, TypeScript, Vite. The flow
  editor is a node graph (React Flow). No YAML editor is built; simple content (FAQ, tools, notices, policy) is edited
  in forms.
- **The studio does not modify `voxstage/`.** It uses the engine as a library (`DomainPack.load`, `load_flows`,
  `evaluate`) and nothing else crosses the boundary. A change the studio needs in the core is reported and becomes an
  item of the engine track in the run queue.
- The studio is a reference and learning implementation, like the engine (project principles, Non-Goals: "A
  production-ready product"). It is built to look and behave like a product (draft, validation, publish, history),
  but v1 has one local user and no authentication; users and roles exist in the schema only.
- The studio track has its own items (ST1 to ST3) in the run queue, separate from the engine items. Its decisions are
  recorded in this folder like every other one.

## Rationale

- Option 1 hides the cost of operating the bot, which the project exists to show. Option 2 splits the story
  ("build it, manage it") across two repositories and lets the contract between them (the YAML files) break without a
  test noticing. Option 4 puts web dependencies in the package that the principles keep small and replaceable ("Keep
  components replaceable").
- Option 3 keeps one test run able to prove the contract: content written by the studio loads in the engine.
- Running the engine's own loader for validation means the studio cannot disagree with the engine about what is valid.
- Node graph over text: every flow node names its successors explicitly (ADR 0010), so a flow already is a directed
  graph; the editor draws what the file says. Public flow builders work the same way (see Public basis).

## Public basis

- [Dialogflow CX: flows and versions](https://docs.cloud.google.com/dialogflow/cx/docs/concept/version) (read
  2026-10-27): a hosted console edits conversation flows as a draft, takes immutable versions, and deploys versions to
  environments. Precedent for a separate operating console with draft and version.
- [React Flow: layouting](https://reactflow.dev/learn/layouting/layouting) (read 2026-10-27): the library has no layout
  engine of its own; Dagre is recommended for tree-like flows. Precedent for keeping layout apart and using a separate
  library for automatic placement.
- [FastAPI: SQL databases](https://fastapi.tiangolo.com/tutorial/sql-databases/) (read 2026-10-27): a session per
  request as a dependency; separate input and output models; Alembic migrations for production.
- Own experiment: a contract test (ST1) imports `domains/`, exports it again, and checks that the engine loads the
  result and that the parsed content equals the source. If it cannot be made to pass, this decision is revisited.

## Consequences

- A new top-level directory with its own dependencies; the engine's `pyproject.toml` does not change. The backend
  installs `voxstage` in editable mode.
- The engine's loader API (`DomainPack.load`, `load_flows`, the error classes) becomes a de facto interface. Changes by
  the engine track are caught by the contract test.
- The loader reports errors as text naming a file and node. The studio parses them for now; structured errors are a
  possible engine-track item (see the design index).
- The studio's lines are outside the effort ledger (they are not rules).

## Open questions

See [docs/studio/README.md](../studio/README.md), "Open decisions".

## Decider's note

(none yet)
