# Spec R10: many slots at once, carry-over, references (C06)

Read first: this file, [queue.md](../queue.md), decision sheet rows R10-1 to R10-6, R7-7, R9-1 to R9-5, R11-1,
`docs/flow-spec.md`, `voxstage/rules/flows.py`, `voxstage/rules/interpreter.py`, `voxstage/normalize/`, the C06
scenario files and the shop C02 and C09 scenarios (the return flow must keep passing them).

## Decisions already made (do not reopen)
- R10-1: captures apply on every turn. The asked slot's extractor takes its value first; other slots take only values
  that cannot be mistaken: `choice` words, or a number next to a cue word declared on the capture; a bare number
  never fills another slot. A new value replaces a filled slot (read back if listed).
- R10-2: no reference rule; missing reference kinds are findings.
- R10-3: node type `form` (`slots` in asking order, filled ones skipped; `say_when_ready`; `next`); the shop return
  flow is rewritten with it; questions inside a form follow the `ask` rules of R6 to R9.
- R10-4: shop `item` is the item name, `item_category` the category for the notice (`item_category ==
  'electronics'`), `size` captured only.
- R10-5: telecom `roaming_setup` with tool `add_feature` [line_last4, feature, duration_days] (risky), cue words
  ending / 끝나는 for the line, extractor `duration` (a number right before day / days / 일 / 일간).
- R10-6: shop tool `create_return` [order_id, item, size] (risky); the return flow ends with a confirm.

## Build
1. Captures on every turn (`flows.py`, `interpreter.py`):
   - a capture may declare `cue: [words]`; with a cue, a `number` or `digits` capture takes only a number within
     two words of a cue word (before or after; a Korean cue matches the start of a word, so 주문에서 has 주문);
   - on the first turn every capture runs as before (a cue is still required when declared);
   - on later turns, while a flow waits at an `ask`, `form` question or `confirm`, after the global commands and the
     corrections: captures for slots other than the asked one run when they are a `choice`, `date`, `month_start`,
     `day`, `time_window` or `duration` capture, or a cued `number` / `digits` capture;
   - at an `ask`: the asked slot is extracted as before and the other captured values are merged; if only other
     slots changed, they are set and the current question is asked again (not a miss);
   - at a `confirm`: if a captured value changes a slot, the slot is set and the confirm is asked again (no tool
     call); otherwise yes / no as before;
   - read-back (R9) runs for listed slots that changed; `trace["captured"]` lists what was taken.
2. Extractor `duration` (`normalize`: `duration_days(text, lang)`; en "ten days", "a day"; ko "십 일", "10일간",
   "십사 일로"): the number right before the unit; usable in asks and captures.
3. Node type `form`: `slots` is a list of ask specs (`slot`, `prompt`, `extractor`, ... as an `ask`, including
   `interruptible`), `say_when_ready` a list of `{needs: [slots], say: <template>}` or `{needs: [...], notices: all |
   [ids]}`, `next`. Run: every `say_when_ready` item whose slots are all known and that was not said yet in this
   flow is said (in list order); then the first unfilled slot is asked and the form waits; when all are filled the
   flow goes to `next`. A waiting form question is handled exactly like a waiting `ask` (commands, corrections,
   button switch, interrupts, side questions, keypad-only, back, park and resume, re-prompt policy). Load checks:
   like `ask` for each slot, `needs` names known slots, notice ids exist.
4. Content (twins):
   - shop `return_request` with a `form` (order number, item; notice when `item_category` is known; intro when the
     item is known), captures `item` (names, colour + item phrases first), `item_category`, `order_id` (cue: order /
     주문), `size` (small / medium / large; 스몰 / 미디엄 / 라지), then a confirm and `create_return`; the notice
     condition in `notices.yaml` becomes `item_category == 'electronics'`; tool `create_return` (risky);
   - telecom `roaming_setup` and tool `add_feature` (risky).
5. `docs/flow-spec.md`: captures on every turn, cues, `duration`, `form`.

## Done when
- C06 base scenarios pass in all three domains and both languages, clean mode.
- C02 and C09 shop, and every earlier result, still pass; regressions listed in the handoff note.
  NullDM 0 and OracleDM 100 percent in both modes.
- Tests: cue before and after the number, Korean cue with a particle; a bare number never fills another slot; a
  choice word changes another slot at an ask and at a confirm; read-back on such a change; `duration` table rows;
  `form`: skip filled slots, say_when_ready once and at the earliest turn, both orders of the return flow, back and
  a side question inside a form; load errors for a bad form.

## Metrics for the handoff note
C06 pass counts (base, variants, noisy) per domain and language; overall pass counts in both modes; lines and nodes
of `return_request` with the form next to the R7-7 branch version (20 / 9); interpreter lines; cue-word failures by
kind (R10-5).
