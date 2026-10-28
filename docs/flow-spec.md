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

## Notices and situation wording (R5)

`domains/<domain>/<lang>/notices.yaml` is the one place for what the bot must say word for word and for the wording
that depends on the situation. It has two sections:

```yaml
notices:                               # required wording; every entry says `fixed: true`
  time_deposit_early_close:
    fixed: true
    priority: 10                       # lower number is spoken first; priorities are unique
    text: "This is a deposit product, ..."   # literal: no {} fields
    applies_when: "item == 'electronics'"    # optional expression over the flow's slots
wording:                               # situation wording; exactly these keys, in every language
  fallback.miss, fallback.exceed, ask.invalid, ask.keypad_only, ask.exceed, flow.attribute_missing, flow.no_flow
```

A `notices` node (`ids:` optional, `next`) says every listed notice (every notice without `ids`) whose `applies_when`
holds, in priority order, as part of the reply. Notices are never cut short (interruption is a streaming question,
S5). Unknown ids and names in conditions fail at load. `rules/config.yaml` keeps only counts and actions; the words
come from `wording`. Changing a sentence is an edit to the registry, not to code.

## Switching (R6)

A flow can break into another flow that is waiting for an answer (decisions R6-1 to R6-6):

```yaml
id: cancel_order
triggers:   {all_of: [[cancel]], any_of: [order], none_of: [how]}   # outside a flow, as before
interrupts: {priority: 5, any_of: [cancel]}                          # while another flow waits at an ask
carry: [order_id]                                                    # slots taken over from the parked flow
```

- A pattern word may be a phrase (`no service`): in English its words must occur next to each other in that order
  (decision R6-7); in Korean spacing is ignored, as before.
- `interrupts:` uses the trigger language plus `priority`. While a flow waits at an `ask`, only the `interrupts:` of
  the other flows are checked; plain `triggers` apply only when no flow waits. Highest priority wins, then the most
  matched words; the match, its priority, specificity and ties are in `trace["interrupt"]`.
- Order at a waiting `ask`: a button of another flow switches; then the interrupts are checked; only when nothing
  matches is the input the answer (re-asked if unusable, as before).
- `interruptible: false` on an `ask` lets nothing in: speech is the answer, and a button counts as an invalid answer.
- A switch parks the running flow as `{flow, node, slots}` on `state.meta["parked"]` (newest last), copies the new
  flow's `carry` slots that the parked flow has, runs its captures, and starts it at `start`. Nothing else carries
  over. The trace has `switch: {from, to, by: interrupt|button}` and `carried`. Resuming a parked flow is R7.
- Load checks: `interrupts` must be a valid pattern; every `carry` name must be a slot of the flow; `interruptible`
  is true or false.

## Side questions and resuming (R7)

Order of checks while a flow waits at an `ask` (decisions R6-4 to R6-6, R7-1 to R7-5):

1. a button of another flow switches (not at `interruptible: false`);
2. the other flows' `interrupts:` (not at `interruptible: false`);
3. the extractor and the FAQ rules are both evaluated, and `decide(extracted, faq)` picks:
   `answer` (a usable value wins), `side_question` (no value, an FAQ match: the FAQ answer, then the pending
   question again; the flow, slots and miss counters do not move), or `reprompt` (as before, counts as a miss).
   `trace` has `extracted`, `faq` and `decided`, so turns where both matched can be counted. The two are evaluated
   one after the other; running them concurrently waits for a new ADR (ADR 0002 keeps `respond` synchronous).

When a flow that was switched in ends:
- without an action: the newest parked flow resumes in the same turn and asks its pending question again, with the
  slots it had (`trace["resumed"]`);
- with `handoff` or `end_call` (also the missing-attribute hand-off): every parked flow is dropped
  (`trace["parked_dropped"]`).

`rules/config.yaml` sets how many flows may be parked: `switch: {max_parked: 2}` (default 2, at least 1). Parking
beyond it drops the oldest, silently, and lists it in `trace["parked_dropped"]`.

## Confirming risky actions (R7b)

A tool that changes something for the caller is marked in `tools.yaml` (decision R7-12):

```yaml
make_transfer:
  params: [amount, to_account]
  risky: true
```

A `call` to a risky tool must be reached only from the `on_yes` of a `confirm` node, and cannot be the start; the
loader rejects anything else, so a flow cannot forget the question.

```yaml
confirm: {type: confirm, prompt: "Shall I send {amount | money('USD')} to your {to_account} account?", on_yes: make, on_no: done}
```

- The keys are `on_yes` / `on_no`, not `yes` / `no`: YAML reads those bare keys as booleans.
- At a waiting `confirm` nothing breaks in: no button switch, no `interrupts:`, no FAQ side question.
- Keypad 1 is yes and 2 is no. Speech is yes when it has a yes word and no no word, no in the opposite case, and
  unclear otherwise. The words are in `domains/<domain>/<lang>/rules/confirm.yaml` (`yes_words`, `no_words`; quote
  "yes" and "no"), required for every pack with a `rules/config.yaml`. Korean answers keep interjections (네, 예,
  아니요), which rule matching otherwise drops (`Tokenizer.analyze_answer`).
- No: the registry wording `confirm.declined` is said and the flow goes to `on_no`; the tool is not called.
  Unclear: the `ask` re-prompt policy (same counter, then hand-off); the tool is never called on it.
- At a keypad-only `ask`, a side question whose spoken words contain digits gets `ask.keypad_only` before the FAQ
  answer (R7-11).

## Global commands (R8)

`domains/<domain>/<lang>/rules/commands.yaml` holds exactly three word-group patterns (decisions R8-1 to R8-5):

```yaml
cancel: {any_of: [cancel, forget it, never mind], none_of: [how, what, why]}
back:   {any_of: [go back, previous]}
agent:  {any_of: [agent, person, human]}
```

They are checked first, for every utterance, in every state (also at a `confirm`); keypad input and buttons are
never commands. Then come the button switch, `interrupts:` and the answer / FAQ of R6 and R7.

- `cancel`: keeps what came with the request (`customer`, `policy` and the other setup values in `meta`) and clears
  the slots, the flow, every parked flow, the question history, `result` and the counters. `flow_id` becomes the
  reserved `main_menu` (no flow file may use that id); the next words are handled as at the start. Reply:
  `command.cancelled`.
- `agent`: `command.agent` and `HandOff("caller_request")`; parked flows are dropped.
- `back`: at a waiting `ask` or `confirm`, the previous answered question is asked again (say, branch and call nodes
  in between are skipped); its old answer stays until a new one replaces it; at the first question that question is
  asked again; outside a flow, `flow.no_flow`. Tool calls already made are not undone. The answered questions are
  in `state.meta["asked"]`, per flow: a parked flow keeps its history and gets it back when it resumes.
- One word can mean two things: "cancel" stops the task in bank and telecom, but in shop "cancel it" or "cancel
  the order" means the `cancel_order` flow. The shop `cancel` command therefore has `none_of` words for an order
  reference; the clash is settled in domain data, not in the core.

## Read-back and corrections (R9)

A misheard value can only be corrected if the caller hears it (decisions R9-1 to R9-5).

- `domains/<domain>/readback_slots.yaml` lists the slots that are read back, each with a formatter
  (`amount: "money('USD')"`, `quantity: count`). When such a slot gets a new value (an answer, a capture, a
  correction), the registry wording `readback` (it contains `{value}`) leads the reply: "$13. To which account?".
  The newest one is kept in `state.meta["readback"]`.
- Right after the global commands, while a flow waits at an `ask` or a `confirm`, an utterance that matches
  `rules/corrections.yaml` (one `correction` pattern, matched on the answer analysis, so Korean keeps 아니요)
  corrects that slot: the number that differs from the current value replaces it, the value is read back and the
  current question (or confirm) is asked again. At a `confirm` a correction needs a number; a bare no declines.
- A correction without a number offers the partner from `rules/confusions.yaml` (`pairs: [[13, 30], ...]`, written by
  hand) with `correction.offer`; yes or keypad 1 takes it, anything else asks the slot's question again.
- An odd correction (only the current value, several differing values, no partner) asks the slot's question again.
- `rules/config.yaml` `correction: {max_corrections: 2, on_exceed: handoff}`: the next correction of the same slot
  says `ask.exceed` and returns `HandOff("correction_failed")` (or `EndCall`).

## Many slots at once and the form node (R10)

Captures apply on every turn, not only to the first words (decisions R10-1 to R10-6):

```yaml
captures:
  size:     {extractor: choice, choices: [small, medium, large]}
  order_id: {extractor: digits, length: 4, cue: [order]}   # only a number within two words of "order"
  duration_days: {extractor: duration}                     # "ten days", "십 일": the unit is the cue
```

- On the first words every capture runs. On later turns, while a flow waits at a question or a `confirm`, only
  values that cannot be mistaken are taken for other slots: `choice` words, `date`, `month_start`, `day`,
  `time_window` and `duration` values, and numbers next to their `cue` words. A bare number never fills another
  slot, and when the asked slot took a value from the words, only `choice` words also fill other slots.
- At a question, other slots that changed are set; if the asked slot got nothing, the question is asked again (not a
  miss). At a `confirm`, a change sets the slot and asks the confirm again, with no tool call. Listed slots are
  read back (R9).
- A Korean cue matches the start of a word (주문에서 has 주문).
- A slot that is not filled is a missing attribute in templates and conditions, so `{size | default('')}` or
  `'size' in slots` handle a slot that is only captured, never asked.

A `form` node asks for what is missing, in order, and says parts of the conversation as soon as they can be said:

```yaml
collect:
  type: form
  slots:                                   # ask specs without next, in asking order; filled ones are skipped
    - {slot: order_id, prompt: "What is your order number?", extractor: digits, length: 4}
    - {slot: item, prompt: "What would you like to return?", extractor: choice, choices: {...}}
  say_when_ready:                          # each said once, in the first turn its slots are all known
    - {needs: [item], say: "I can help you start that return."}
    - {needs: [item_category], notices: all}
  next: confirm
```

A waiting form question is handled exactly like a waiting `ask` (commands, corrections, switches, side questions,
keypad-only slots, `back`, park and resume, the re-prompt policy).

## Identity gate (R13)

Protected information is gated by tool, not by flow (decisions R13-1 to R13-3):

```yaml
# domains/<domain>/tools.yaml
get_balance:     {requires: verified, params: [account_last4], ...}   # refused until the caller is checked
verify_identity: {verifies: true, params: [account_last4, pin], ...}  # the check; exactly one when a tool is protected
```

- A `call` of a protected tool before the check calls nothing: the running flow is set aside (`meta["gated"]`) and
  the domain's verification flow starts, with the slots it lists in `carry`. When the check passes, the stopped call
  runs in the same turn, so one turn holds `verify_identity` and then the protected call. A pass holds for the rest
  of the call (`meta["verified"]`, kept by `cancel`).
- The verification flow (`role: verification`) has no triggers, buttons, interrupts or captures; it asks what the
  check needs (asks for carried slots are skipped), calls the `verifies` tool and must not call a protected tool.
  Which details are asked is content, so another sign-in method (phone number plus date of birth) is another flow
  file and tool, not engine code (backlog D6). Its questions follow the `ask` rules.
- A failed check empties the answers the verification flow took, so its questions are asked again, and the flow
  goes on to its `on_error` node (wording that does not say which part was wrong). After `max_attempts` failures
  (`rules/config.yaml` `verification: {max_attempts: 3, on_exceed: handoff}`, or the gated flow's own
  `verification: {max_attempts: N}`) the call is locked: `verify.locked` and `HandOff("verification_failed")` (or
  `EndCall`), and every later protected call gets the same reply without a call.
- `prefill: {account_last4: customer.account_last4}` fills an empty slot from the caller's record when a flow
  starts; words the caller said win.

## Tool failures and delays (R12)

A failed tool never makes the bot invent an answer (decisions R12-1 to R12-5):

```yaml
# domains/<domain>/tools.yaml
get_balance:
  retry: 1                       # a timeout is tried once more, silently; never on a risky tool
  rules:
    - {when: {account_last4: "0001"}, delay_ms: 8000, return: {...}}   # a slow answer (simulated)
# rules/config.yaml
tools: {max_failures: 2, on_exceed: handoff, timeout_ms: 5000}
```

- An answer slower than `timeout_ms` is a `timeout`; its data is not used.
- A `timeout` of a tool with `retry: 1` is called once more; both calls are recorded. Other errors (not_found,
  invalid_credentials) are never retried.
- A `timeout` of a risky tool may have done the change, so the bot says `call.unconfirmed` and hands off
  (`HandOff("outcome_unknown")`); a clear refusal of a risky tool goes to the flow's `on_error`.
- Timeouts that remain count over the call; at `max_failures` the bot says `call.exceed` and hands off
  (`HandOff("tool_failed")`, or `EndCall`). Errors caused by what the caller gave are not counted.
- `on_error` is optional: without it a failed call says `call.failed` and the flow ends.
- A timeout of the verifying tool (R13) is not a failed check: the bot says `call.failed` and the stopped flow is
  dropped.

## Node types

| Type | Fields | Behaviour |
|---|---|---|
| `say` | `text`, `next` | Adds the rendered text to the reply. |
| `ask` | `slot`, `prompt`, `extractor`, `length` (digits only), `choices` (choice only), optional `interruptible` (default true), `next` | Adds the prompt and waits. The next turn's input fills the slot; if it contains no value, the prompt is asked again (see the re-prompt policy above). |
| `form` | `slots`, optional `say_when_ready`, `next` | Asks the first empty slot and waits; says ready parts once; then `next` (see above). |
| `confirm` | `prompt`, `on_yes`, `on_no` | Asks yes or no and waits; required before a risky tool (see above). |
| `call` | `tool`, `args`, `on_ok`, optional `on_error` | Calls the tool through the tool port. The result is `result` (`{error: code}` on failure); failures follow R12. |
| `branch` | `cases: [{when, next}]`, `else` | First case whose expression is true; otherwise `else`. |
| `notices` | optional `ids`, `next` | Says the applicable registry notices in priority order. |
| `goto` | `next` | Jumps. |
| `end` | optional `action: handoff` (with `reason`) or `end_call` | Ends the flow; the action is returned in `DMResult.actions`. |

Extractors: `text` (the words as given), `digits` (one run of digits, keypad digits, or digits said one by one:
"four eight two one", "사팔이일"; optional exact `length`), `number` (the first number, written or spoken:
"twenty five hundred", "이천오백", "두 개"), `choice` (the first of `choices` found in the words), and since R11
`date` (an ISO date), `month_start` (the first day of the month referred to: "starting next month" -> the 1st),
`day` (a day of the month: "the twentieth", "이십 일") and `time_window` (morning / afternoon / evening).

## Numbers, dates and the clock (R11)

Spoken values are read by `normalize/voxstage_normalize/` (its own package since R11-4; before that `voxstage/normalize/`), a self-contained package (it imports nothing else from
`voxstage`; decision R11-1) for English and Korean, covering what the datasets need. Numbers that are part of a date
("the fifteenth", "십오일") are not numbers. Korean native numerals count only before a counter (두 개), so 네 (yes)
is never four; a numeral at the start of a Korean word counts only when the rest of the word is a unit, a counter,
a particle, 일 or 월, so 이체 or 오전 are never numbers.

`date` and `month_start` need the scenario clock, `setup.now` (in `state.meta["now"]`); without it they fail like a
missing attribute (apology and hand-off). Dates follow fixed rules, written to `trace` (decision R11-2): a day
without a month, or a month and day without a year, is the nearest date not in the past; Korean "다음 주 X요일" is
that weekday of the next calendar week; English "next Monday" said on a Monday is next week's. Only an English
"next / this + weekday" whose weekday still lies ahead this week has two readings: the bot says `date.ambiguous`
with both dates numbered 1 and 2 (not a miss) and takes keypad 1 / 2 or one of the two dates.

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
fills; bad extractors; file name differing from the id; a protected tool called with no verification flow, two
verification flows, or a verification flow that does not call the `verifies` tool or calls a protected one. Korean and English flows are twins: the same node ids,
types, `next` links, tools and arguments; only texts and triggers differ (a test enforces it).

## Policy values (R14)

A reply that holds a rule value (free transfers, the free-shipping threshold, the grace period) is a small flow:
a trigger, one `say` with `{policy.<key> | formatter}` and `end`. The value comes from `setup.policy` of the request,
so changing the rule is one edit outside the flows. FAQ answers stay fixed text. A missing key apologises and
hands off (R4-2).

The hard-coded counter-example (R14-1) is kept as files: `domains_variants/hardcoded/shop/` holds the three shop replies
with the v1 threshold written into the texts. `python -m voxstage.policy_impact` lays it over a copy of `domains/`, runs
C12 under v1 and v2 for both variants, and shows the flow files and lines a move to v2 must edit and how many replies
still say the old threshold after the single edit the C12 case points to.

## Not yet

(nothing in the rule engine; R15 closes S1.)
