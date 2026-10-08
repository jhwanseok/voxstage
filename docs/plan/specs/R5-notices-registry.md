# Spec R5: notices and situation wording (C09)

Read first: this file, [queue.md](../queue.md), decision sheet rows R5-1 and R5-2, `docs/flow-spec.md`,
`voxstage/domain_pack.py`, `voxstage/rules/faq.py`, `voxstage/rules/interpreter.py`.

## Decisions already made (do not reopen)
- R5-1: one registry file per domain and language. It holds the fixed notices and the situation wording, so
  wording depends on the situation (fallback type, re-ask) and can be customized. Fixed notices carry `fixed: true`.
- R5-2: when several notices apply they are all spoken in a fixed priority order and are never interrupted.

## Build
1. `domains/<d>/<lang>/notices.yaml`:
   `notices: {id: {text, priority, fixed: true, applies_when: <expression, optional>}}` and
   `wording: {<situation key>: text}`. Required situation keys: `fallback.miss`, `fallback.exceed`,
   `ask.invalid`, `ask.keypad_only`, `ask.exceed`, `flow.attribute_missing`, `flow.no_flow`.
   Every required key must exist in every language (load-time check). Notice text is literal, never templated.
2. Node type `notices` (`ids` optional): says every listed notice whose `applies_when` holds, ordered by
   `priority` (lower number first), as one reply segment. Unknown ids are a load-time error.
3. Move the wording out of `rules/config.yaml` (fallback replies, ask replies) into the registry; the config
   keeps counts and actions only. The managers read wording through the pack.
4. First flows (twins): `time_deposit_signup` and `checking_signup` (bank), `return_request` (shop, notice
   depends on the item), `change_plan` (telecom, notice depends on downgrade).

## Done when
- The C09 scenarios of all three domains pass in both languages (positive and negative).
- Tests: priority order with two applicable notices, `applies_when`, missing situation key, unknown id,
  literal text, wording used by fallback and ask.
