# R16a: types, roles and call binding (A1 of ADR 0014)

Read first: [ADR 0014](../../decisions/0014-typed-attributes-roles-and-api-binding.md) (accepted), decision sheet rows
A-0014, B-0014, C-0014, D-0014, P8-0014, `docs/flow-spec.md`.

## Goal

A domain can describe the people and values its flows collect as typed records, name two uses of one type in a flow
(booker and visitor), and bind each parameter of an API call to a role field, an earlier call's result or a constant.
Nothing in the existing flows changes.

## Built in this item (ADR parts 1, 2, 4)

- `domains/<d>/types.yaml`: `types` (records of scalar fields, extractor names as field types, optional per-language
  `label`) and `session_roles` (only `caller`). No nesting (decision D).
- Flow header `roles: {name: {type, default: {from: other role}, label}}`.
- `ask` (and `form` slots) with `role` and `field` instead of `slot`; the slot is stored as `<role>.<field>`, the
  extractor is the field's unless the ask says its own. Templates and expressions read `{visitor.name}`.
- `confirm` with `role_default: <role>`: yes copies the source role's fields to the role, no goes on to the asks;
  a role with a `default` and no such node is a load error (P3).
- `call` with `bind` per parameter: `{role, field}`, `{call: <step id>, field}`, `{const}`; `args` and `bind` never
  name one parameter; together they name every parameter of the tool (P2). An unbound source at run time is a missing
  attribute (R4-2).
- `caller`: after the identity check passes, the fields of the `caller` type that the verifying call's arguments carry
  are kept for the rest of the call; `{role: caller, field: ...}` reads them (decision B).
- Bank: `types.yaml`, flows `book_visit` and `visit_status` (en and ko), tools `book_visit` and `get_visit`
  (protected), capability C14 with three twin scenarios.

## Not in this item

API parameter types, required flags, response schema, structured load errors and the data-flow check (A2, R16b);
state tracking per role and corrections of role fields (S2-2); the studio screens (ST4).

## Done when

- `types.yaml` loads and rejects nesting, unknown field types and session roles other than `caller`.
- The loader rejects: unknown role or field, `slot` with `role`, `args` and `bind` for one parameter, missing
  parameters, a `call` binding to a step that is not another call of the flow, `role_default` without a default and a
  default without the node, a default source that is not another role of the same type.
- C14 passes 3/3 in both languages and both modes; no earlier capability regresses.
- Tests in `tests/test_roles.py`; the full suite passes.
