# Decision records

Every design decision that shapes the engine gets one record here. The format follows
Michael Nygard's [Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
(title, context, decision, status, consequences) with three additions this project needs:

- **Decided by**: the person who made the call. Code may be written with AI assistance;
  decisions are made by the repo owner, and the record says so.
- **Options considered**: what was on the table, so the choice can be re-examined later.
- **Public basis**: at least one independent public source, *or* a statement that none was
  found and which experiment in this repo will validate the choice instead
  (see "Public basis" in [project-principles.md](../project-principles.md)).

A record's *Rationale* says whose reasoning it is. If the decider adopted an option after
reading an analysis, the record says that, and the decider may add their own words under
*Decider's note*.

| # | Decision | Status |
|---|---|---|
| [0001](0001-turn-input-model.md) | Turn input is a tagged union of frozen value objects | accepted |
| [0002](0002-dialogue-manager-contract.md) | Dialogue managers are stateless; state is explicit data | accepted |
| [0003](0003-rule-engine-representation.md) | S1 rules are declarative YAML run by an interpreter | accepted |
| [0004](0004-dummy-api-tool-executor.md) | Tool calls go through a ToolExecutor port with a declarative fake API | accepted |
| [0005](0005-dataset-first-development.md) | Datasets come first; capabilities are built one problem at a time | accepted |
| [0006](0006-english-first.md) | Datasets are English first; Korean is added later | accepted |
| [0007](0007-korean-dataset-alongside-english.md) | A Korean dataset is added alongside the English one | accepted |
| [0008](0008-evaluation-harness.md) | Evaluation harness: constructor wiring, canonical slot comparison, no reactive-rule label | accepted |
| [0009](0009-faq-rule-manager.md) | FAQ rule manager: word groups, held-out text, configurable N-miss escalation | accepted |
| [0010](0010-flow-interpreter.md) | Flow interpreter: state-machine map, small expression language, handler registry, load-time validation | accepted |

## Template

```
# NNNN. Title
Status: proposed | accepted | superseded by NNNN
Date:
Decided by:

## Context
## Options considered
## Decision
We will ...
## Rationale
## Public basis
## Consequences
## Open questions
## Decider's note
```
