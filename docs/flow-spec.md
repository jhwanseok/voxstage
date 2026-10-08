# Flow files

Flows describe a conversation as data. One generic interpreter (`voxstage/rules/interpreter.py`) runs them for any
domain and language (decisions: [0003](decisions/0003-rule-engine-representation.md),
[0010](decisions/0010-flow-interpreter.md)). Files live in `domains/<domain>/<lang>/flows/<flow id>.yaml`; the file
name is the flow id. Everything below is checked when the file is loaded.

```yaml
id: order_status
triggers: {all_of: [[order, package], [my]], any_of: [where, status], none_of: [how, cancel]}   # word groups, as in the FAQ rules
start: ask_order
nodes:
  ask_order: {type: ask, slot: order_id, prompt: "What is your order number?", extractor: digits, length: 4, next: lookup}
  lookup:    {type: call, tool: get_order_status, args: {order_id: "{order_id}"}, on_ok: route, on_error: say_fail}
  route:
    type: branch
    cases:
      - {when: "result.status == 'shipped'", next: say_shipped}
    else: say_fail
  say_shipped: {type: say, text: "Your order has shipped and should arrive on {result.eta}.", next: done}
  say_fail:    {type: say, text: "I'm unable to check that order right now.", next: done}
  done: {type: end}
```

## Node types

| Type | Fields | Behaviour |
|---|---|---|
| `say` | `text`, `next` | Adds the rendered text to the reply. |
| `ask` | `slot`, `prompt`, `extractor`, `length` (digits only), `choices` (choice only), `next` | Adds the prompt and waits. The next turn's input fills the slot; if it contains no value, the prompt is asked again. |
| `call` | `tool`, `args`, `on_ok`, `on_error` | Calls the tool through the tool port. The result is `result` (`{error: code}` on failure). |
| `branch` | `cases: [{when, next}]`, `else` | First case whose expression is true; otherwise `else`. |
| `goto` | `next` | Jumps. |
| `end` | optional `action: handoff` (with `reason`) or `end_call` | Ends the flow; the action is returned in `DMResult.actions`. |

Extractors: `text` (the words as given), `digits` (one run of digits, or keypad digits; optional exact `length`),
`number` (the first number), `choice` (the first of `choices` found in the words). Spoken numbers such as
"twenty five hundred" arrive with R11.

## Templates and expressions

`{...}` in `text`, `prompt` and `args` holds an expression; `{{` and `}}` are literal braces. `branch` conditions are
expressions too. Names: the flow's slots (every `ask` slot), `slots`, `customer`, `policy`, `result`. Allowed:
constants, attribute access on mappings, constant-index access, comparisons (`== != < <= > >= in not in`), `and or not`,
`+ - * / // %`, `a if c else b`, list and tuple literals, and calls to `len lower upper int str`. Everything else
(lambdas, comprehensions, calls to other functions, underscore attributes, assignments, imports) fails at load.
Expressions are parsed with Python's `ast` and walked by a small evaluator; they are never `eval`ed.

## What the loader checks

Unknown node types and keys; missing, unreachable or looping nodes (a loop must wait for the caller); a flow
without an `end`; tools that do not exist and arguments that do not match the tool's parameters; names no `ask`
fills; bad extractors; file name differing from the id. Korean and English flows are twins: the same node ids,
types, `next` links, tools and arguments; only texts and triggers differ (a test enforces it).

## Not yet

Buttons and keypad menus starting a flow (R3), number and date formatting (R4), notices (R5), switching and
resuming (R6, R7), cancel and hand-off words (R8), correction (R9), identity gate (R13).
