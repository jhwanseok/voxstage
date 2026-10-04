# 0004. Tool calls go through a ToolExecutor port with a declarative fake API

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

Several capabilities need external data: answering from an attribute plus an API result,
falling back when an API fails, blocking information until identity is verified. Real
back-ends are not available and would make experiments unrepeatable.

## Options considered

1. **Fake API driven by a rule table**: the result depends on the call's arguments, written
   as data (`domains/<name>/tools.yaml`) and run by a generic executor.
2. **Per-domain Python fake functions**: flexible, but domain code would have to be loaded
   by the core.
3. **Local HTTP mock server**: closest to a real integration (latency, failures), but adds a
   process to every run.

## Decision

We will use option 1: a `ToolExecutor` port (`voxstage/tools.py`) with `FakeApiExecutor`,
which answers from per-tool rules matched on the arguments, supports error rules to
simulate failures, and records every call for tool-call accuracy checks.

## Rationale

- The decider asked for a dummy API that "handles input arguments by rules".
- Rules as data keep the "core never imports domain code" property and make the fake
  backend part of the dataset, reviewable in a diff.
- Behaviour depends only on arguments, so any run can be repeated exactly.
- Cost accepted: the fake cannot express stateful backends (a transfer that changes a
  balance). If a capability needs state, this decision is revisited.

## Public basis

- [τ-bench (Yao et al., 2024)](https://arxiv.org/abs/2406.12045) evaluates agents in domains
  with API tools and policy guidelines, which supports testing against simulated
  domain back-ends.
- Martin Fowler, [Test Double](https://martinfowler.com/bliki/TestDouble.html): a *fake* is a
  working implementation that takes shortcuts unsuitable for production.
- Alistair Cockburn, [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/):
  isolate the application from external systems behind ports with swappable adapters.

## Consequences

- Managers receive a `ToolExecutor`; the fake and a future real client are interchangeable.
- A dataset scenario may expect specific tool calls; a test checks that every expected call
  is answerable by the domain's `tools.yaml`.
- Matching compares values as strings, because YAML may read `4821` as an integer while a
  keypad input arrives as the string `"4821"`.

## Open questions

- Whether the fake should later be exposed over local HTTP to include transport latency and
  failures. Not needed until the API-failure capability (C10) is built.

## Decider's note

"dummy API를 만들어서 실행하도록 하자. input 인자별로 룰을 만들어서 처리하는 로직일거같아."
