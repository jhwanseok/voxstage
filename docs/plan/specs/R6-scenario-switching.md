# Spec R6: scenario switching (C01)

Read first: this file, [queue.md](../queue.md), decision sheet rows R6-1 to R6-6 and R4-3, `docs/flow-spec.md`,
`voxstage/rules/flows.py`, `voxstage/rules/interpreter.py`, `voxstage/rules/matching.py`, the C01 scenario files.

## Decisions already made (do not reopen)
- R6-1: on a switch the old flow is parked, not abandoned: its flow, node and slots are kept on a stack in the
  state. R6 only parks; resuming is R7.
- R6-2: only declared slots carry over. The new flow lists them (`carry: [order_id]`); a listed slot is copied when
  the parked flow has a value. Nothing carries over by a shared name alone.
- R6-3: when two interrupts match, the highest priority wins, then the most matched words; the choice and the ties
  go to `trace`.
- R6-4: the incoming flow declares `interrupts:` (word patterns and priority). Only those are checked while another
  flow runs; plain `triggers` apply outside a flow only. A node with `interruptible: false` lets nothing in.
- R6-5: at a waiting `ask` the interrupts are checked first; only when none matches is the input the answer.
- R6-6: a button that starts another flow switches at a waiting `ask` (no `interrupts:` needed) and parks the
  running flow; at a node with `interruptible: false` the press counts as an invalid answer, as before.
- R4-3: `captures` and the word -> value `choices` mapping stay as built in R4.

## Build
1. Flow file keys (`voxstage/rules/flows.py`, load-time checks):
   - `interrupts: {priority, all_of, any_of, none_of}` at the top of a flow, in the trigger pattern language;
     `priority` is an integer (default 0).
   - `carry: [slot, ...]` at the top of a flow; each name must be a slot of this flow (an `ask` slot or a
     capture), and a sensitive slot may be carried (it was already given on the keypad).
   - `interruptible: false` on an `ask` node (the only node that waits); any other value than a boolean is an
     error.
2. Interpreter (`voxstage/rules/interpreter.py`): while a flow waits at an `ask`:
   - a `ButtonPress` for another flow's button switches (R6-6), unless the node has `interruptible: false`;
   - an `Utterance` is matched against the `interrupts:` of every other flow first (R6-5, R6-3). A match
     switches; otherwise the input is the answer, as before. Nothing is checked at an `interruptible: false` node.
   A switch parks the running flow as `{flow, node, slots}` on `state.meta["parked"]` (a list, newest last; no
   depth limit until R7-3), copies the new flow's `carry` slots from the parked slots, runs the new flow's
   captures on the utterance, resets the re-prompt counter and starts the new flow at `start`. The trace records
   `switch: {from, to, by: interrupt|button}`, the interrupt match (priority, specificity, ties) and `carried`.
   A flow that has ended does not park; the next utterance uses the plain triggers as before.
3. New flows (English and Korean twins). The fake API has no blocking, cancelling or outage tool and adding tools
   is a dataset change, so each flow says what happens next and hands off to a person (`end` with
   `action: handoff` and a reason); nothing is claimed as done.
   - bank `card_loss`: says that the card can be reported and blocked, then hands off (`card_loss`).
   - shop `cancel_order`: `carry: [order_id]`; asks the order number if it is not known, then hands off
     (`cancel_order`) naming the order.
   - telecom `outage_report`: says to restart the phone once and that an outage report will be taken, then hands
     off (`outage_report`).
   Each has `triggers` (outside a flow) and `interrupts` (inside one).
4. `change_plan` triggers also accept the plain "change my plan" (en `change`, ko `변경`, `바꾸`), because C01
   telecom starts with it; the direction is then asked as before. Check that C09 telecom still passes.
5. `docs/flow-spec.md`: a section "Switching (R6)" with the keys above and the order of checks at an `ask`.

## Done when
- The C01 scenarios of all three domains pass in both languages, clean mode (base scenarios). Variant copies and
  noisy mode are measured and reported; failures are findings, not tuned.
- C04, C08 (shop, telecom) and C09 still pass; NullDM 0 percent and OracleDM 100 percent unchanged.
- Tests: interrupt switches at an `ask`; no switch at `interruptible: false`; plain triggers do not fire inside a
  flow; priority then specificity with ties in `trace`; parked stack content; declared carry copies and an
  undeclared same-name slot does not; button switch at an `ask` and the guarded case; load errors for a bad
  `carry` name, a bad `interruptible` value and a bad `interrupts` pattern.

## Metrics for the handoff note
C01 pass counts per domain and language (base, variants, noisy); overall pass counts with flows (en of 234, ko of
240); interpreter and flow-loader lines; flow YAML lines and nodes of the new flows; number of interrupt patterns;
held-out FAQ queries taken over by the new triggers (FAQ-only numbers are unchanged by construction).
