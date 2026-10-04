# 0001. Turn input is a tagged union of frozen value objects

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

The pipeline so far accepts audio only. Customer-service voice flows also receive keypad
digits (DTMF) and button presses, and those are deterministic: they carry no recognition
error. The capability catalog (numeric input by button, slot correction after ASR errors)
needs the dialogue layer to know which kind of input it received.

## Options considered

1. **Tagged union**: frozen dataclasses `Utterance | Dtmf | ButtonPress` combined into one
   `TurnInput` type, handled with `match`.
2. **Class hierarchy**: an abstract `TurnInput` with subclasses and polymorphic methods.

## Decision

We will use option 1. See `voxstage/turn.py`.

## Rationale

(Analysis presented to the decider, who chose this option.)

- Inputs are plain data with no behaviour of their own, so inheritance buys nothing.
- Frozen dataclasses make accidental mutation impossible and serialize cleanly into events.
- `match` on class patterns keeps each dialogue manager's input handling in one readable
  block, and `describe()` fails loudly on an unhandled kind.
- Cost accepted: a new input kind needs edits in the union and in each `match` that cares.

## Public basis

- [PEP 634, Structural Pattern Matching: Specification](https://peps.python.org/pep-0634/):
  class patterns work on dataclass instances (dataclasses get `__match_args__`). This is
  the language mechanism the choice relies on. It supports feasibility only; the
  data-over-hierarchy argument is design reasoning, not a cited result.

## Consequences

- The pipeline's audio path produces an `Utterance` after ASR; DTMF and button inputs enter
  the dialogue layer directly.
- Events gain an `input` record with the input kind.

## Open questions

- Whether `Utterance` should later carry the ASR n-best list (needed for some slot
  correction strategies). Decide when that capability is implemented.

## Decider's note

(none recorded)
