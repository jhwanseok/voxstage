# Spec R7: side question, then return (C02)

Read first: this file, [queue.md](../queue.md), decision sheet rows R7-1 to R7-8 and R6-1 to R6-7,
`docs/flow-spec.md`, `voxstage/domain_pack.py`, `voxstage/rules/faq.py`, `voxstage/rules/flows.py`,
`voxstage/rules/interpreter.py`, the C02 scenario files, and the C01 and C09 scenario files of shop and telecom
(they must keep passing).

## Decisions already made (do not reopen)
- R7-1: inside a flow only an FAQ match is a side question: the FAQ answer is said, then the pending question is
  asked again; the flow does not move. Moving to another flow stays with R6 (`interrupts:`).
- R7-2: filled slots stay; only the pending question is asked again.
- R7-3: FAQ side questions do not stack. The stack is the R6 parked flows: at most 2, set in `rules/config.yaml`;
  when a third would be parked the oldest is dropped and the drop goes to `trace`; nothing is said and the switch
  goes ahead.
- R7-4: at an `ask` both the slot extraction and the FAQ rules are evaluated every turn, and one pure function
  `decide(extraction, faq)` picks: a usable answer wins; otherwise an FAQ match is answered and the question asked
  again (not counted as a miss); otherwise the re-prompt as before. Both results go to `trace`. They are evaluated
  one after the other now; concurrency waits for a new ADR (ADR 0002 keeps `respond` synchronous until S5).
- R7-5: when a switched-in flow ends without an action, the newest parked flow resumes in the same turn and its
  pending question is asked again. After `handoff` or `end_call` all parked flows are dropped (in `trace`).
- R7-6: tool `make_transfer` (`[amount, to_account]`, default `{reference: TR1001}`, no failure rule) and flow
  `transfer` (amount, receiving account savings or checking, call, say amount, account and reference, or an
  apology). No confirmation before the call until R9. Bank C02's last turn is a spoken number and waits for R11.
- R7-7: shop `return_request` branches in YAML on `'item' in slots`: item known: intro and notice, then the order
  number; item not known: order number, item, then intro and notice. No `form` node (that is R10-3).
- R7-8: telecom `change_plan` asks the plan (basic or plus), then the direction, then intro and notice; both can be
  captured from the first words.
- The R6 order of checks stays in front: a button of another flow, then `interrupts:`, then R7-4.

## Build
1. `decide(extraction, faq)` in `voxstage/rules/interpreter.py`: a pure function over the two results (a value or
   None; an FAQ match or None) returning one of `answer`, `side_question`, `reprompt`. At a waiting `ask` (after the
   R6 checks) the manager runs the extractor and the FAQ matcher (`FaqRuleManager`'s matching, without its miss
   counter), calls `decide`, and acts:
   - `answer`: as before.
   - `side_question`: reply = FAQ answer, a space, the pending prompt rendered with the current slots. State stays at
     the same node; slots unchanged; `ask_misses` unchanged; the FAQ fallback counter unchanged.
   - `reprompt`: as before (counts as a miss).
   `trace` gets `extracted` (value or None), `faq` (matched entry id or None) and `decided`. A sensitive slot's
   spoken answer is still refused (R3-1); the FAQ may still answer it as a side question.
   The FAQ is used only when the pack has FAQ rules; without them `decide` sees None.
2. Resume and drop (R7-5): when a run ends at an `end` node and `state.meta["parked"]` is not empty:
   - no action: pop the newest parked entry, continue in the same turn: reply = the ended flow's words, a space,
     the parked node's prompt rendered with the parked slots; state = the parked flow, node and slots.
     `trace["resumed"] = {flow, node}`.
   - `handoff` or `end_call` (including the missing-attribute hand-off): clear `parked`;
     `trace["parked_dropped"] = [flow ids]`.
3. Parked limit (R7-3): `rules/config.yaml` gets `switch: {max_parked: 2}` (integer >= 1, default 2 when the
   section is absent; unknown keys are load errors), read into the pack. Parking beyond the limit drops the oldest;
   `trace["parked_dropped"]` lists it. Add the section to every domain's config in both languages.
4. Content:
   - `domains/bank/tools.yaml`: `make_transfer` as in R7-6 (shared by both languages).
   - `transfer` flow (twins): triggers on transfer / send money words without fee, limit or abroad words (they
     belong to `transfer_fee` and the FAQ); `to_account` choices: en savings, checking; ko 저축, 적금 -> savings,
     입출금, 체크 -> checking (same values); amount by the `number` extractor.
   - `return_request` (twins): the R7-7 branch; `order_id` digits, length 4.
   - `change_plan` (twins): the R7-8 order; `plan` choices as in `plan_price`.
5. `docs/flow-spec.md`: a section "Side questions and resuming (R7)": the order of checks at an `ask`, `decide`,
   resume and drop, `switch.max_parked`.

## Done when
- C02 of shop and telecom passes in both languages (clean mode, base scenarios); bank C02 is listed in the handoff
  note as waiting for R11, with a test that its first two turns behave as the scenario expects.
- C01, C04, C08 (shop, telecom) and C09 still pass; NullDM 0 percent and OracleDM 100 percent unchanged.
- Tests: `decide` table (four combinations); side question keeps node, slots and the miss count; FAQ miss at an ask
  is a re-prompt; resume after an action-less end with the parked prompt; drop after hand-off; parked limit drops
  the oldest; `switch` config validation; `transfer` flow calls `make_transfer` with both slots; `return_request`
  both orders; `change_plan` with and without captures.

## Metrics for the handoff note
C02 pass counts per domain and language (base, variants, noisy); overall pass counts with flows (en of 234, ko of
240); number of turns across the suite where extraction and FAQ both matched (from `trace`); interpreter lines;
lines and nodes of `transfer`, `return_request` (before and after the branch) and `change_plan`; held-out FAQ
queries taken over by the new triggers.
