# R16b: API types, response schema and the load-time flow check (A2 of ADR 0014)

Read first: [ADR 0014](../../decisions/0014-typed-attributes-roles-and-api-binding.md) (accepted; parts 3 and 5, details
P1, P4, P6), [R16a](R16a-types-roles-binding.md), `docs/flow-spec.md`.

## Goal

`tools.yaml` says what each API takes and returns, and the loader refuses a flow that cannot call it correctly:
a required parameter nobody binds, a value of the wrong type, or a value that some path through the flow never
collects. Each problem is a structured item, so the studio can point at the node and the parameter.

## Built in this item

- **Typed parameters.** `params` is either the old list of names or a mapping
  `name: {type, length, choices, required}`. `type` is one of `text digits number choice date month_start day
  time_window duration` (the field types of `types.yaml`); `choices` lists the allowed words of a `choice`;
  `required` defaults to true. The list form means "every name, required, untyped" and keeps working.
- **Response schema.** `returns` maps a returned field to `{type}` or to the type name alone; `boolean` is allowed here
  (`verified: true`). A tool without `returns` is untyped as before.
- **Fake API rules (P6).** `rules[].when` names declared params; `return` names declared `returns` fields; the values
  have the declared types. Checked when `tools.yaml` loads, so the fake API and the spec cannot drift.
- **Optional parameters (P4).** `required: false`: a call that binds nothing for it leaves it out of the arguments.
  The fake API refuses only missing required params.
- **Structured load errors (P1).** The flow check reports every problem of a flow at once as
  `{code, node, parameter, role, field, path}`:
  - `unbound`: a required parameter has no `args` or `bind` entry; or a `{call, field}` source names a field the
    earlier tool does not declare in `returns`.
  - `type_mismatch`: the source's type does not fit the parameter's (role field or flat slot extractor vs the param;
    returned field vs the param; a constant that does not satisfy the param's type, length or choices).
  - `not_collected`: on some path from `start` to the call node the value is not collected first; `path` is one such
    witness path of node ids ending at the call node. `role` and `field` name the value; for a flat slot `role` is
    null and `field` is the slot name; for a call source `role` is null and `field` is `<step>.<field>`.
  The error is `FlowCheckError` (a `FlowError`): `.items` is the list; its message is built from the items.
- **Data-flow check.** A value is collected by an `ask` of that role field or slot (also as a `form` slot), by a
  `confirm` with `role_default` on its `on_yes` edge, and a call result by the `on_ok` edge of that call. `caller`
  fields count as collected when the called tool is `requires: verified`. A flat slot that no `ask` or `form` of the
  flow fills (a capture, a prefill) is not checked, since a capture may fill it from the first utterance.
  Whether a path exists that avoids every collector is decided by a search over the node graph, so loops, `branch`
  and `goto` are covered. `back` and `cancel` need no special case: `back` returns to an earlier node and continues
  along the same edges, and `cancel` leaves the flow.
- **`args` with one placeholder** (`"{order_id}"`, no other text, no formatter) is read as binding that slot or role
  field and is checked like a `bind`; any other template is left as it is.
- Shipped `tools.yaml` of the three domains are written in the typed form.

## Not in this item

State tracking per role and corrections of role fields (S2-2); nested types (decision D); studio screens (ST4, which
reads `.items`); calling a real HTTP API.

## Done when

- Old list-form `tools.yaml` and `args` flows load unchanged; the typed shipped files load and the dataset still scores
  as before (all earlier capabilities and C14, both languages, both modes).
- Each code has a test that produces it, with the item fields as above; several problems in one flow are reported
  together; a loop and a `branch` that skips the `ask` are covered by tests.
- The fake API rule checks reject a `when` on an undeclared param, a `return` field not in `returns` and a value of the
  wrong type.
- Tests in `tests/test_flowcheck.py`; the full suite passes.
