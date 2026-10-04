# 0003. S1 rules are declarative YAML run by an interpreter

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

S1 is the rule-based baseline. A goal of the project is to measure how a rule engine's
complexity grows as capabilities are added, and to compare it fairly with LLM stages. A
weak rule baseline would make that comparison meaningless.

## Options considered

1. **Declarative YAML flows plus an interpreter**: domain packs hold `flows/*.yaml`; a generic
   interpreter runs them.
2. **Hand-written Python state machine** per domain.

## Decision

We will use option 1.

## Rationale

(Analysis presented to the decider, who chose this option.)

- It keeps domain content as data, which the domain-pack rule ("core never imports domain
  code", verified by a zero core diff when a domain is added) depends on.
- It resembles how rule-based dialogue systems are commonly authored, so the baseline is
  not a straw man.
- Complexity becomes measurable in two places: YAML lines and states per capability, and
  the interpreter's own growth. Both are recorded; counting only the YAML would flatter
  the rule approach.
- Cost accepted: the interpreter itself must be written and will grow with each capability.

## Public basis

- [Schema-Guided Dialogue (Rastogi et al., 2020)](https://arxiv.org/abs/1909.05855): domains
  described declaratively and consumed by general dialogue models, supporting the idea of
  separating domain description from engine code.
- No public source was found for the specific complexity metrics (lines, states, change
  impact). They are this project's own and will be validated by the S1 experiments.

## Consequences

- The Interpreter pattern is used (see `docs/design-patterns.md`).
- Each capability added to S1 records its authoring effort so the complexity curve can be
  drawn.

## Open questions

- YAML schema for flows (nodes, transitions, slot collection). To be proposed and decided
  with the first capability that needs it.

## Decider's note

(none recorded)
