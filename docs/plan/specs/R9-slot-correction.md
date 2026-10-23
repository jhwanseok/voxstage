# Spec R9: slot correction after misrecognition (C05)

Read first: this file, [queue.md](../queue.md), decision sheet rows R9-1 to R9-5, R7-12, R8-1 to R8-5, R11-1,
the ADR 0011 amendment, `docs/flow-spec.md`, `voxstage/domain_pack.py`, `voxstage/rules/interpreter.py`,
`voxstage/normalize/`, and the C05 scenario files. C05 is scored in noisy mode: in clean mode its first turn expects
the misheard value and fails by design.

## Decisions already made (do not reopen)
- R9-1: slots listed in `domains/<d>/readback_slots.yaml` are read back implicitly: when one is filled, its value
  (written with a formatter) leads the next reply; no yes / no question.
- R9-2: corrections are recognised by patterns in `rules/corrections.yaml`, only while a read-back slot exists, and
  correct the slot read back most recently; the new value is the number that differs from the current value; only a
  correction without a new value uses the hand-written `rules/confusions.yaml`, offering the partner in one question.
  Table entries count as rules.
- R9-3: an odd correction (only the current value, two or more differing numbers, a bare no without a partner) asks
  the slot's question again (an ordinary answer, under the ask re-prompt policy); a no to the offered partner does the
  same; more than `correction.max_corrections` (default 2) corrections of one slot hand off on the next.
- R9-4: shop `change_quantity` with tool `update_quantity` [order_id, quantity]; telecom `data_plan` with tool
  `set_data_plan` [plan_gb]; both risky. Read-back slots: bank `amount`, shop `quantity`, telecom `plan_gb`. The
  correction check comes right after the global commands.
- R9-5: correction patterns are matched on `Tokenizer.analyze_answer` (Korean keeps 아니요, 아뇨).

## Build
1. Files and loaders (`voxstage/domain_pack.py`):
   - `domains/<d>/readback_slots.yaml`: `readback_slots: {<slot>: "<formatter call>"}` (for example
     `amount: "money('USD')"`, `quantity: count`), language-free; the formatter must exist (load error otherwise).
   - `rules/corrections.yaml`: exactly one pattern `correction` (word groups); `rules/confusions.yaml`:
     `pairs: [[13, 30], ...]` (integers, no number in two pairs). Both required for every pack with a
     `rules/config.yaml`.
   - `rules/config.yaml` gets `correction: {max_corrections: 2, on_exceed: handoff}` (validated like `ask`).
   - New required wording keys: `readback` (contains `{value}`, the only wording with a placeholder; it is replaced,
     not templated) and `correction.offer` (contains `{value}`).
2. Read-back (interpreter): at the end of a run, every read-back slot whose value changed in this turn (an answer, a
   capture, a correction) puts `readback` with the formatted value before the reply; the newest one is kept in
   `state.meta["readback"]` for corrections. `trace["readback"]` lists them.
3. Corrections (interpreter), checked right after the global commands while a flow waits at an `ask` or a `confirm`
   and `meta["readback"]` names a filled slot of that flow:
   - the utterance matches `correction` (on `analyze_answer`); at a `confirm` it must also contain a number, so a
     bare no there stays a decline;
   - numbers of the utterance (via `normalize`) that differ from the current value: exactly one distinct value: the
     slot takes it, the read-back runs, and the current question (or confirm) is asked again with the new value;
   - no number at all: the confusion partner of the current value is offered (`correction.offer`); the next answer:
     a yes word (from `confirm.yaml`) or keypad 1 takes it, anything else asks the slot's question again;
   - anything else (only the current value, several differing values, no partner): the slot's question is asked
     again (the node becomes that `ask`; the old value stays until a new answer, as `back` does);
   - each correction of a slot counts in `meta["corrections"]`; past `max_corrections` the reply is `ask.exceed` with
     `HandOff("correction_failed")` (or `EndCall`).
   `trace["correction"]` says what happened.
4. Content (twins): `readback_slots.yaml` for the three domains, `corrections.yaml`, `confusions.yaml` (en and ko:
   13/30, 14/40, 15/50, 16/60, 17/70, 18/80, 19/90), the two tools and flows of R9-4, the new wording.
5. `docs/flow-spec.md`: a section "Read-back and corrections (R9)".

## Done when
- C05 base scenarios pass in noisy mode in all three domains and both languages.
- Earlier results hold (both modes); every regression is listed in the handoff note. NullDM 0 and OracleDM 100.
- Tests: file validation (unknown formatter, bad pair, missing file, config keys, wording placeholders); read-back
  after an answer and after a capture; correction with one new value (ask and confirm); correction keeps other slots;
  bare no at a confirm declines; bare no at an ask offers the partner and both answers to the offer; odd corrections
  re-ask; the correction limit; Korean 아니요 corrections.

## Metrics for the handoff note
C05 pass counts (noisy, base and variants) per domain and language; overall pass counts in both modes; number of
correction patterns and confusion pairs; interpreter lines; new flows' lines and nodes.
