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

## Open questions (to be decided before S3)

- `reply` is a complete string. An LLM-backed manager streams tokens, and the existing
  latency segments T3 (first token) and T3b (first speakable sentence) depend on that.
  Options when S3 starts: (a) add a streaming variant of `respond`, (b) keep the string
  contract and measure LLM latency inside the manager's trace. Not decided yet.
- Where tool calls execute. Currently a manager can only *return* actions
  (`HandOff`, `EndCall`); nothing runs external APIs. Decide when the "answer from API
  results" capability is implemented.

## Decider's note

(none recorded)
