# 0002. Dialogue managers are stateless; state is explicit data

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

Rule-based, hybrid, LLM and agent managers will implement one contract so the same
scenarios can be run against each stage and compared. The project also records everything
as events, and wants any session to be reproducible from its log.

## Options considered

1. **Stateless manager, explicit state**: `respond(state, input) -> (reply, new state, actions)`.
2. **Stateful object**: the manager holds the conversation state and exposes `respond(input)`.

## Decision

We will use option 1. See `voxstage/dialogue.py` (`DialogueManager`, `DialogueState`,
`DMResult`, `step`).

## Rationale

(Analysis presented to the decider, who chose this option.)

- A session can be replayed by feeding recorded inputs through a manager from the initial
  state; tests assert this.
- Two managers can be run on identical inputs and states, which the stage comparison needs.
- No hidden state: what the manager knew at a turn is in the log.
- Cost accepted: callers carry the state object; `evolve` must be used instead of mutation.

## Public basis

- Martin Fowler, [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html): state
  can be rebuilt by re-running the logged events. This is the same replay idea applied to
  dialogue state.
- Gamma et al., *Design Patterns* (1994), Strategy: interchangeable algorithms behind one
  interface, here the four manager implementations.
- [Schema-Guided Dialogue (Rastogi et al., 2020)](https://arxiv.org/abs/1909.05855) treats
  dialogue state as explicit data tracked across turns.

## Consequences

- `step()` is the only place that emits dialogue events and owns the turn counter.
- Known limit: `DialogueState` is frozen, but its `slots` and `meta` dicts are ordinary
  dicts. Managers are required to use `evolve` (which copies them); this is enforced by
  tests and review, not by the type system.

## Open questions

- None open. Both questions raised at acceptance were decided on 2026-10-05; see the
  amendment below and [0004](0004-dummy-api-tool-executor.md).

## Amendment 2026-10-05: streaming waits for S5

`reply` stays a complete string until S5. A streaming `respond` is not added now.
Decided by jhwanseok. Consequence: before S5 the LLM-backed managers (S3, S4) cannot expose
first-token timing through this contract, so the existing T3 / T3b segments apply only to the
original pipeline path. Latency of an LLM manager before S5 is recorded as total manager
time (`wall_s` on `dm_response`). The streaming interface is designed when S5 starts.

Where tool calls execute: decided in 0004 (a `ToolExecutor` port; managers call it).

## Decider's note

On streaming: "스트리밍은 S5에 적용하자. 너무 복잡해질것 같아."
