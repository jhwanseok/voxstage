# Spec R2: flow interpreter

Read first: this file, [queue.md](../queue.md), ADR 0003, 0004, 0010, 0011, `voxstage/dialogue.py`, `voxstage/tools.py`,
`voxstage/rules/faq.py` (from R1), `voxstage/evaluate.py`. Do not read other plan files.

## Goal
Domains describe conversations as YAML; one generic interpreter runs them. After this step the core never changes
when a flow is added. English and Korean.

## Decisions already made (do not reopen)
ADR 0010: state-machine map with explicit `next`; `{}` template fields plus a small expression language and
`branch` nodes for conditions; node types dispatched through a registry; validation at load time.

## Schema (`domains/<d>/<lang>/flows/<id>.yaml`)
```yaml
id: balance_inquiry
triggers: {any_of: [balance, how much money]}   # same word-group language as R1
start: ask_account
nodes:
  ask_account: {type: ask, slot: account_last4, prompt: "Which account? Please enter the last four digits.",
                extractor: digits, next: lookup}
  lookup:      {type: call, tool: get_balance, args: {account_last4: "{account_last4}"},
                on_ok: say_balance, on_error: say_fail}
  say_balance: {type: say, text: "Your balance is {result.balance} {result.currency}.", next: done}
  say_fail:    {type: say, text: "I could not look that up right now.", next: done}
  done:        {type: end}
```
Node types: `say`, `ask` (slot, prompt, extractor, next), `call` (tool, args, on_ok, on_error), `branch`
(`cases: [{when: <expr>, next: id}]`, `else: id`), `goto` (next), `end`. State lives in `DialogueState`
(`flow_id`, `node_id`, `slots`, tool result under `meta["result"]`). Extractors: `text`, `digits`, `number`
(digits and plain numerals only; spoken numbers come in R11), `choice` (list of allowed words).

## Expression language (default grammar, see the decision sheet)
Parsed with `ast.parse(mode="eval")`, checked against a node whitelist at load time, evaluated by a small
tree walker. Never `eval`. Allowed: constants (str, int, float, bool, None); names for `slots`, `customer`,
`policy`, `result`; attribute access and constant-index access; comparisons (`== != < <= > >= in not in`);
`and or not`; `+ - * / // %`; conditional expression; calls only to whitelisted functions
(`len`, `lower`, `upper`, `int`, `str`). Everything else is a load-time error naming the file, node and column.
Used in `branch` conditions and in template fields as `{expr}`; plain `{slot}` and `{result.field}` are expressions too.

## Build
1. `voxstage/rules/expr.py`: parse, validate, evaluate. Whitelists are constants.
2. `voxstage/rules/interpreter.py`: `FlowManager(DialogueManager)` with a node-handler registry
   (`register_node("say")(fn)`), the loop that runs nodes until the manager must wait for the caller
   (an `ask` without a value) or the flow ends, flow selection by `triggers` (R1's matcher), and `HandOff`
   or `EndCall` through `actions` when the flow says so.
3. Load-time validation in `voxstage/rules/flows.py`: unknown node types, missing or unreachable nodes, unknown
   `next` targets, `start` missing, `branch` without `else`, tool names that are not in `tools.yaml`, expression
   errors, slot names used in templates that no `ask` or `call` can have filled.
4. First flows, in English and Korean: `balance_inquiry` (bank), `order_status` (shop), `data_usage` (telecom),
   each a lookup flow without the identity gate (that is R13). Use tools and values from the domain's `tools.yaml`.
   The Korean flow is a twin of the English one: same flow id, node ids, `next` links, tools and arguments;
   only prompts, texts and `triggers` are Korean (triggers use the Kiwi matcher of R1). A test enforces the twin rule.
   Spoken Korean numbers are not extracted here (R11); `digits` accepts digits only.
5. Pattern note: add the registry and the expression evaluator to `docs/design-patterns.md` (where, why, what was rejected).

## Metrics
Interpreter lines (`voxstage/rules/interpreter.py` plus `flows.py` plus `expr.py`, counted separately), nodes
per flow, lines per flow, expression operators used, and the core diff when the second and third domain's
first flow is added (target: zero lines under `voxstage/`).

## Done when
- Each of the three flows, in both languages, runs end to end against the fake API in a test, including the error branch
  (`0000` timeouts), and the lookup parts of the C04 and C08 scenarios behave as their `expect` says where they
  do not depend on later steps; list the ones that must wait.
- Validation tests: one failing example per check; expression tests: allowed forms evaluate, each disallowed
  form (lambda, comprehension, attribute call, import, assignment) is rejected at load.
- Adding the shop and telecom flows changed no file under `voxstage/` (verify with `git diff --stat` and write
  the result in the handoff note).
- All tests pass; ledger row appended; `NullDM` and `OracleDM` results unchanged.

## Stop and report
- If a flow needs something the schema cannot say, do not extend the schema silently: write the case as an
  open question in the handoff note (it feeds the write-up hook).

## Write-up hook
"A tiny flow interpreter: what the YAML can and cannot say."
