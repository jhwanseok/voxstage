# 0010. Flow interpreter: schema, expression language, dispatch, validation

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

Step R2 realises ADR 0003: domains describe conversations as YAML and one generic interpreter runs them.

## Options considered

1. Schema: node list with implicit order; state-machine map with explicit transitions.
2. Templates: `{}` fields only; plus a small expression language.
3. Dispatch of node types: registry of handlers; `match` statement; a class per node.
4. Validation: at load time; during the call.

## Decision

1. **State-machine map**: every node names its successor, so jumps are visible in the file.
2. **`{}` fields plus a small expression language**, and `branch` nodes stay as the place for conditions.
   The language is a restricted subset (see the R2 spec): comparisons, boolean and arithmetic operators,
   attribute and index access on slots, customer, policy and tool results, and a whitelist of functions.
3. **Registry of handlers** keyed by node type.
4. **Load time**, including reachability and reference checks.

## Rationale

- 1: R6 to R8 (switching, resuming, escaping) are jumps; a list would be replaced then.
- 2: the decider wants an expression language as well. The assistant's concern: a rich one turns the
  interpreter into a programming language and hides rule complexity there. Mitigation: the ledger counts
  expression operators and the expression-evaluator lines as interpreter complexity.
- 3: new node types in later steps are added without touching core code.
- 4: errors surface before a call, as in the dataset loader.

## Public basis

- [Schema-Guided Dialogue (Rastogi et al., 2019)](https://arxiv.org/abs/1909.05855): declarative service descriptions.
- Public precedent for small, non-Turing-complete expression languages (for example CEL) is a candidate
  and must be opened and read before it is cited. Rasa flows likewise.

## Consequences

- Expressions are parsed with Python's `ast` and checked against a node whitelist at load time; they are never `eval`ed.
- The first lookup flows (`balance_inquiry`, `order_status`, `data_usage`) are English only.

## Decider's note

"좋은 제안인거 같아" (state-machine map) / "작은 식언어도 추가해야 해. branch 노드로 분리하는 건 좋아." /
"맞아 레지스트리 방식이 적절해" / "좋아." (load-time validation)
