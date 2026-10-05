# 0008. Evaluation harness: how managers are wired, how slots are compared, no reactive-rule label

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

Step R0 builds the scorer every later step is judged by. Three choices shape it: how a manager
receives tools and scenario setup, how a slot value is compared with the expected one, and
whether rules written after a failure are tracked separately.

## Options considered

1. Wiring: (A) constructor arguments, `setup` copied into `state.meta` once; (B) tools and
   setup passed on every `respond` call.
2. Slot comparison: (A) exact string; (B) exact after a light canonical form; (C) full normalisation.
3. Reactive rules: (A) the owner labels each rule written after a failure; (B) a mechanical rule
   (added after the case's first evaluation); (C) no separate label.

## Decision

1. **A.** A manager gets its tools and domain pack in its constructor. `setup` is copied into
   `state.meta` in `initial_state`.
2. **B.** `slots` are compared as exact strings after a canonical form that strips currency symbols
   and currency words attached to a number, and thousands separators. So `"$500"`, `"500 dollars"`,
   `"500달러"` and `"1,250"` match `"500"` and `"1250"`. Nothing else is normalised.
3. **C.** No reactive-rule label. Every rule counts the same in the effort measure, whenever
   it was written. Git history already shows when a rule arrived.

## Rationale

- 1: `meta` does not change between calls within a session, so passing it every time adds nothing,
  and the contract of ADR 0002 stays as it is.
- 2: the decider wants symbol-attached values to pass more easily, while keeping matching strict
  otherwise. Cost accepted: C07 can no longer detect a manager that outputs `"$2,500"` instead of
  `"2500"`; it still measures spoken numbers to digits and relative dates to ISO dates.
- 3: the decider's view is that a rule is a rule: for the comparison with LLM stages it is
  rule-based either way. The assistant had proposed the label to expose overfitting to the test
  set; that risk is handled instead by the held-out rule in ADR 0009.

## Public basis

- [τ-bench (Yao et al., 2024)](https://arxiv.org/abs/2406.12045) scores by end state rather than wording.
- No public source for the canonical form or the effort metrics; the harness experiment validates them.

## Consequences

- One constant defines the canonical form, so changing the symbol list is a one-line edit.
- Currency words and symbols are a list in code until backlog item D1 (currencies) revisits them.
- The ledger no longer has a reactive-share column.

## Decider's note

"R0-1는 A안이 합리적 실질적으로 호출마다 진행될때 meta가 바뀌는 경우는 없을것 같아" /
"정확한 문자열 일치가 필요해보이긴 해. 다만 달러같은 기호가 붙을 때는 통과가 더 잘되야 하는 걸 명심해" /
"반응형 률이 왜 필요한지 모르겠어. 반응형이든 처음부터든 결국 Rule Based 라는 측면에서 같은 걸로 평가해야되는거 아냐?"
