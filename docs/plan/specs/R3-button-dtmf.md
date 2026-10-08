# Spec R3: button and keypad input (C04)

Read first: this file, [queue.md](../queue.md), decision sheet rows R3-1 and R3-2, `docs/flow-spec.md`,
`voxstage/rules/interpreter.py`, `voxstage/rules/flows.py`.

## Decisions already made (do not reopen)
- R3-1: spoken values are accepted at a keypad prompt through the same extractor. For personal-information
  slots (birth date, phone number and similar) the prompt is keypad only: a spoken value is not accepted.
  Declared once per domain as a list of sensitive slots; an `ask` for one must use the `digits` extractor
  (checked at load time).
- R3-2: two re-prompts, then hand off on the third invalid input. The count and the action
  (`handoff` / `end_call`) are configurable. A spoken answer at a keypad-only prompt counts as invalid.

## Build
1. A flow may declare `buttons: [menu_balance]`. A `ButtonPress` with that id, received while no `ask` waits,
   starts the flow. A button id may belong to one flow only (load-time check). Button ids are language-free,
   so English and Korean twins carry the same list.
2. `domains/<domain>/sensitive_slots.yaml` (`sensitive_slots: [...]`, language-free like `tools.yaml`).
   Loaded into the pack. An `ask` whose slot is listed must use `extractor: digits`, else a load-time error.
3. Runtime: at a keypad-only `ask` an `Utterance` is rejected with the keypad wording; at any `ask` an
   invalid value re-asks. Both increase `state.meta["ask_misses"]`; a valid value or a new `ask` resets it.
   After more than `max_reprompts` invalid inputs the manager emits `HandOff("input_failed")` or `EndCall()`.
4. Config in `rules/config.yaml`: `ask: {max_reprompts: 2, on_exceed: handoff, invalid_reply, keypad_reply,
   exceed_reply}` (the wording moves to the registry in R5).
5. The trace records `{"ask": node, "extracted": ..., "misses": n}`.

## Done when
- The C04 scenarios of all three domains pass in English and Korean.
- Tests: button starts a flow; unknown button falls to the FAQ rules; sensitive slot rejects speech and accepts
  digits; the load-time check; two re-prompts then handoff; `end_call` setting; counter resets on success.
- NullDM and OracleDM unchanged; ledger row appended.
