# 0014. Typed attributes, roles and API binding

Status: proposed (draft for review; nothing here is decided until the owner answers the questions at the end)
Date: 2026-10-28
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

A bank bot has a `user`, but the person who books a branch visit and the person who comes can be different people. An
API has one fixed spec, while each scenario collects different attributes; to call the API the two must be linked.
The owner raised this while reviewing the studio.

What the engine does today (`docs/flow-spec.md`, `voxstage/tools.py`, `voxstage/rules/`):

- A slot is a flat, untyped name. A flow's `captures` only say how to read it (`extractor: digits | choice | date |
  duration ...`); an `ask` node names the slot and its extractor. There is no "a person" or "an account" and no
  field inside a slot.
- `tools.yaml` has `params: [account_last4, pin]`, a list of names. No type, no required flag, no response schema.
  Rules and defaults return arbitrary maps.
- A `call` node passes values by template text: `args: {order_id: "{order_id}"}`. The result is read back as untyped
  `result.<key>`.
- Some state is per session, not per flow: the identity gate (`requires: verified`, `verifies: true`, R13) and the
  request's `meta` (`customer`, `policy`).
- The loader checks that names resolve, but not that every path to a `call` has collected what the call needs.

Consequences seen so far: the same slot name cannot mean two people ("name" of the booker or the visitor); a tool
cannot say which of its params are required; a typo in a template shows only at run time; and the studio has nothing
to draw a typed form from (ST2 would have to invent the model).

## Options considered

1. Keep flat slots; add a naming convention (`booker_name`, `visitor_name`). Cheapest, but gives no types, no check,
   and every combination of a person's fields becomes its own slot.
2. Typed values and roles, with explicit binding (described below). More engine work, and the loader can check it.
3. Adopt an external schema standard whole (full JSON Schema / OpenAPI for everything, including dialogue state).
   Familiar, but far larger than the engine needs and does not model roles or "who is speaking".

## Proposed decision (to be confirmed question by question)

We will build option 2 as a small, closed model, in this order of increasing scope. Each part is a separate question
below; the part is only built when it is answered.

1. **Type dictionary** per domain (`types.yaml`): a named type is a record of typed fields or a scalar with a rule.
   ```yaml
   types:
     Person:  {fields: {name: text, phone: phone, customer_id: {type: text, length: 8}}}
     Account: {fields: {last4: {type: digits, length: 4}, kind: {type: choice, values: [checking, savings]}}}
     Money:   {scalar: number, unit: currency}
   ```
   Field types are the extractors that already exist (`digits`, `choice`, `date`, `duration`, number), so the
   interpreter reads a field with the same code; what is new is the grouping and the name.
2. **Roles**: a role is a name for a use of a type, with a scope.
   ```yaml
   roles:
     booker:  {type: Person, scope: flow}
     visitor: {type: Person, scope: flow, default: {from: booker, ask: "Is the visitor you?"}}
     caller:  {type: Person, scope: session, filled_by: verify_identity}
   ```
   A role is filled by asking (`ask` node with `role: visitor, field: name`), by a default taken from another role
   after a yes/no, by a tool result, or by the identity gate. `caller` replaces the ad-hoc session state of R13 without
   changing how the gate behaves.
3. **API spec**: `params` become typed and required:
   ```yaml
   get_balance: {params: {account_last4: {type: digits, length: 4, required: true}}, returns: {balance: number, currency: text}}
   ```
   A subset of JSON Schema (type, enum, length, required) is enough and keeps the studio able to read it; the full
   OpenAPI document format is not adopted (option 3).
4. **Binding in the `call` node**: each parameter names its source, one of a role path (`visitor.name`), an earlier
   call's result (`lookup.result.id`) or a constant. The old template form `args: {order_id: "{order_id}"}` keeps
   working: the loader reads it as binding a flat slot, so no existing flow changes.
5. **Load-time check** (the loader, so the studio's publish refuses a bad draft): every required param is bound; a
   bound source has the right type; and on every path of the flow graph a role's field is collected before the call
   that reads it (a data-flow pass over the graph, with `branch` and the `back`/`cancel` commands taken into account).
6. **S2-2 dialogue state**: state tracking holds values per role and field. A correction ("not me, my sister") names
   a role, so the read-back list of R9 (slots that are read back and may be corrected) lists role fields, and a
   correction replaces one field of one role, not a flat name.
7. **Evaluation**: new cases that the flat model cannot pass by construction: booker different from visitor (both
   remain distinct through a correction), the visitor defaulting to the booker, a caller's verified details reused
   without asking again, and a draft with an unbound param refused at load. These are scored on the existing harness as
   a new capability (the next free `C14`) in both languages, for S1 and for S2 later.

The engine stays rule-based underneath: roles and types change what is stored and checked, not how an utterance is
matched.

## Consequences

- The studio (ST2/ST3) can draw typed forms and show unbound params, because the model exists in data, not in code.
- Part 1, 3, 4 and 5 are loader and data changes with a back-compatible reading of today's files. Part 2 and 6 touch
  the interpreter and the dialogue state.
- The load-time data-flow check is new code with its own test burden (graphs with branches and loops).
- The size of a domain pack grows (a `types.yaml`); the effort ledger gets a column for it.

## Public basis

Read 2026-10-28; only what was checked on the page is stated.

- [Dialogflow CX parameters](https://docs.cloud.google.com/dialogflow/cx/docs/concept/parameter): form parameters are
  declared on a page with `entityType`, `required`, `defaultValue`; filled values are written to the session, whose
  parameters are read as `$session.params.<id>`; a composite parameter has named members; webhooks receive
  parameters in `sessionInfo.parameters` and `pageInfo.formInfo.parameterInfo`. Supports typed, required, named
  values and session scope; it has no check that every path fills a parameter before use (not stated on that page).
- [Rasa slots reference](https://rasa.com/docs/reference/primitives/slots.md): slot types `text`, `bool`,
  `categorical`, `float`, `any`, `list`; mappings `from_llm`, `controlled`, and NLU-based `from_entity`,
  `from_intent`. Slots are typed and have a source, but are flat key-values (no record of fields).
- [Amazon Lex V2 composite slot types](https://docs.aws.amazon.com/lexv2/latest/dg/composite-slots.html): a composite
  slot combines two or more sub-slots filled from one utterance; sub-slots are built-in or custom types and a
  composite cannot be a sub-slot (no nesting).
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0) and
  [JSON Schema](https://json-schema.org/): the shape for typed parameters and responses of option 3 and the subset of
  part 3 (cited from general knowledge of the standards, not re-read for this draft).

None of the three bot platforms was found to name a "role" for the same type used twice in one scenario; this is why
the draft proposes it, and why the evaluation in part 7 is the validation. This statement covers the pages read, not
every product.

## Questions for the owner (one at a time; not all at once)

Order, so the load is spread: Q50 (S2 embedding model, already open), then A, B, C, D below, each after the previous.

- A. Scope of the first build: types and roles (parts 1, 2, 4) only, then API typing and the load check (3, 5), then
  the DST link (6) with S2-2? Recommendation: yes, in two builds (A1 = 1, 2, 4 in the flow engine, A2 = 3, 5), 6 goes
  with S2-2.
- B. Is the session role `caller` the same thing as the identity gate (replace R13's state) or a separate role?
  Recommendation: the same; the gate fills `caller`.
- C. Does a field have a fixed list (Person.name, phone, customer_id) per domain, or can the studio add fields?
  Recommendation: per domain in `types.yaml`, editable in the studio.
- D. Is nesting allowed (a Person with an Address record)? Recommendation: no nesting in v1, like Lex.
