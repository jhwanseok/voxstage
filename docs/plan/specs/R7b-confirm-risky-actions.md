# Spec R7b: confirmation before risky actions, and two R7 follow-ups

Read first: this file, [queue.md](../queue.md), decision sheet rows R7-10 to R7-12, R5-1, R3-1, R3-2,
`docs/flow-spec.md`, `voxstage/tools.py`, `voxstage/domain_pack.py`, `voxstage/rules/flows.py`,
`voxstage/rules/interpreter.py`.

## Decisions already made (do not reopen)
- R7-12: a tool is marked `risky: true` in `tools.yaml` (now only `make_transfer`). A `call` to a risky tool must be
  reached only from the `yes` of a `confirm` node (load error otherwise). Node `confirm` (`prompt`, `yes`, `no`) is
  never interruptible and takes no FAQ side question. Yes and no words per domain and language in
  `rules/confirm.yaml`; keypad 1 = yes, 2 = no. No: the tool is not called, the registry wording `confirm.declined`
  is said and the flow goes to `no`. An unclear answer follows the `ask` re-prompt policy (2 re-prompts, then
  hand-off); the tool is never called on it. This is action confirmation; R9-1 stays about slot values.
- R7-10: Korean receiving-account words are only 저축 -> savings and 입출금 -> checking.
- R7-11: at a keypad-only `ask`, a side question whose spoken input contains digits gets the `ask.keypad_only`
  wording before the FAQ answer; without digits, the FAQ answer alone; neither counts as a miss.

## Build
1. `voxstage/tools.py`: tool key `risky` (boolean, default false) accepted and validated. `flows.py` reads the risky
   tool names with the params. Load check: for a `call` node whose tool is risky, every node that leads to it must be
   a `confirm` node whose `on_yes` is that `call`, and the `call` is not the flow's `start`.
2. Node type `confirm` in `flows.py` (`prompt` template, `on_yes`, `on_no`; no other keys; waits for the caller;
   the keys are not `yes` / `no` because YAML reads those bare keys as booleans) and its
   handler in the interpreter (says the prompt and waits). A turn at a waiting `confirm`:
   - no switch, no interrupts, no FAQ (R6 and R7 checks are skipped);
   - `Dtmf` "1" is yes, "2" is no; an `Utterance` is yes when it has a yes word and no no word, no when it has a no
     word and no yes word (words matched with the pack's tokenizer); anything else is unclear;
   - yes: run from `on_yes`; no: say `confirm.declined`, then run from `on_no`; unclear: the `ask` re-prompt policy with
     the confirm prompt (same counter, same hand-off). `trace` gets `confirm: yes|no|unclear`.
3. `domains/<d>/<lang>/rules/confirm.yaml`: `{yes_words: [...], no_words: [...]}` (quoted words; English `"yes"`
   and `"no"` must be quoted for the same YAML reason), non-empty word lists, no shared word; required
   for every domain and language that has a `rules/config.yaml`; read into the pack. A flow with a `confirm` node in
   a pack without confirm words is a load error.
4. Registry: `confirm.declined` becomes a required situation key; text in all six `notices.yaml` files.
5. Content: `make_transfer` gets `risky: true`; the `transfer` flow (twins) gets a `confirm` node between the account
   question and the call, prompt naming the amount and the account; `on_no` goes to `done`. Korean account words per
   R7-10.
6. R7-11 in the interpreter's side-question branch.
7. `docs/flow-spec.md`: the `confirm` node, `risky`, `confirm.yaml`, and the R7-11 rule.

## Done when
- Tests: yes calls the tool once; no does not call it and says `confirm.declined`; keypad 1 and 2; both words or
  neither is unclear; unclear three times hands off without a call; no switch, interrupt or FAQ at a `confirm`;
  load errors: risky call not after a confirm `yes`, risky call reached from elsewhere too, risky call as start,
  confirm without words, bad `confirm.yaml`, missing `confirm.declined`; R7-11 with and without digits.
- Every case that passed after R7 still passes (en 123/234, ko 116/240); NullDM 0 and OracleDM 100 percent.

## Metrics for the handoff note
Overall pass counts; interpreter and loader lines; `transfer` lines and nodes; number of risky tools.
