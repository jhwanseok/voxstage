# Spec R4: answers from attributes and API results (C08)

Read first: this file, [queue.md](../queue.md), decision sheet rows R4-1 and R4-2, `docs/flow-spec.md`,
`voxstage/rules/flows.py`, `voxstage/rules/expr.py`.

## Decisions already made (do not reopen)
- R4-1: a formatter per type chosen in the template (`money`, `date`, `count` first) because the right form
  depends on the TTS spec. An unknown formatter name is a load-time error.
- R4-2: attributes have three sources. (1) What the caller can supply: ask the caller. (2) API results and
  (3) request `meta` values: fail when missing. A default is possible only as an explicit setting in the flow.
  A failure says apology wording, then hands off.

## Build
1. Template syntax `{expression | formatter}` or `{expression | formatter(arg)}`; `default(value)` is the
   explicit default filter. Formatters live in `voxstage/rules/formatters.py` in a registry keyed by name; they
   take the value, the language and arguments. First set: `money` (USD and KRW), `date` (ISO date), `count`.
2. A missing field (`result.x`, `customer.x`, `policy.x`) raises `MissingAttribute`. The manager turns it into
   the `attribute_missing` wording plus `HandOff("missing_attribute")`; with `default(...)` the default is used.
3. Sources: `slots` and bare slot names = caller; `result` = API; `customer` and `policy` = request meta.
   Documented in `docs/flow-spec.md`.
4. A flow may declare `captures`: slots read from the words that started the flow (`extractor: choice` or
   `number`), so "How much is the plus plan" fills `plan`. An `ask` for a slot that is already filled is skipped.
5. First flows (English and Korean twins): `transfer_fee` (bank), `shipping_fee` (shop), `plan_price` (telecom).
   The existing lookup flows use the formatters.

## Done when
- C08 scenarios of shop and telecom pass in both languages. Bank C08 depends on spoken numbers ("five hundred")
  and waits for R11; list it in the handoff note.
- Tests: each formatter, unknown formatter at load, missing attribute fails with handoff, explicit default,
  captures, skipping a filled `ask`.
