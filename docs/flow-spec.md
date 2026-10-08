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

## Buttons, keypad and the re-prompt policy (R3)

- `buttons: [menu_balance]` at the top of a flow lists the button ids that start it (language-free, so twins share
  it; one flow per id). A button received while no `ask` waits starts the flow at `start`.
- An `ask` accepts keypad digits and, unless the slot is sensitive, a spoken value through the same extractor.
- `domains/<domain>/sensitive_slots.yaml` lists the slots that may only arrive on the keypad (birth date, phone
  number). Speech is not accepted for them; an `ask` for one must use `extractor: digits` (load-time check).
- An unusable answer (no value, wrong length, speech at a keypad-only prompt, any other input) re-asks. After
  `ask.max_reprompts` re-prompts (default 2) the manager returns `HandOff("input_failed")` or `EndCall()` as
  `ask.on_exceed` says (`rules/config.yaml`). The counter is `state.meta["ask_misses"]`; a valid answer resets it.

## Attributes, formatters and captures (R4)

Where a value comes from decides what happens when it is missing (decision R4-2):

| Source | Names in templates and expressions | If it is missing |
|---|---|---|
| The caller | slot names, `slots` | The flow `ask`s for it. An `ask` whose slot is already filled is skipped. |
| An API result | `result` | The reply is the apology wording and `HandOff("missing_attribute")`. Nothing is invented. |
| The request's `meta` | `customer`, `policy` | Same as an API result. |

A default is possible only as an explicit filter in the flow: `{result.balance | default('unknown')}`. It is never silent.

`{value | formatter(args) | default(...)}` writes values for speech. Formatters (`voxstage/rules/formatters.py`):
`money(currency)` (USD and KRW; other currencies are backlog D1), `count`, `date` (ISO date). They depend on the
language and, later, on the TTS in use, so the choice is data. An unknown formatter or the wrong number of
arguments fails at load; a value a formatter cannot write (`money('EUR')`, `date` of a non-date) fails like a
missing attribute at run time.

`captures: {plan: {extractor: choice, choices: {플러스: plus}}}` at the top of a flow reads slots from the words that
started the flow ("How much is the plus plan" fills `plan`). `choices` is a list of words or a word -> value
mapping. Free text and sensitive slots cannot be captured. Spoken numbers ("five hundred") are R11.

## Node types

| Type | Fields | Behaviour |
|---|---|---|
| `say` | `text`, `next` | Adds the rendered text to the reply. |
| `ask` | `slot`, `prompt`, `extractor`, `length` (digits only), `choices` (choice only), `next` | Adds the prompt and waits. The next turn's input fills the slot; if it contains no value, the prompt is asked again (see the re-prompt policy above). |
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

Notices (R5), switching and
resuming (R6, R7), cancel and hand-off words (R8), correction (R9), identity gate (R13).
