# Spec R0: evaluation harness (text mode) and effort ledger

Read first: this file, [queue.md](../queue.md) (run protocol), ADR 0002, 0004, 0008, and
`voxstage/dialogue.py`, `voxstage/tools.py`, `voxstage/dataset.py`. Do not read other plan files.

## Goal
Score any `DialogueManager` on the dataset (both languages), and count how much a rule base costs.

## Decisions already made (do not reopen)
ADR 0008: manager gets tools and domain pack in its constructor, `setup` goes to `state.meta` in
`initial_state`; slots compared as exact strings after a canonical form (see below); no reactive-rule label.

## Build
1. `voxstage/evaluate.py`
   - `run_scenario(manager_factory, scenario, tools, mode)`: builds the manager, `initial_state` from `setup`
     (copied into `state.meta`: `customer`, `now`, `policy`), then each turn through `dialogue.step()`.
   - Input mode `clean` (`text`) or `noisy` (`asr_text` when present, else `text`). Button and DTMF turns
     become `ButtonPress` and `Dtmf`.
   - Variants: each variant text runs as an extra copy of that scenario with that turn's text replaced; the id
     is `<id>#v<turn>.<n>`.
   - FAQ: each entry yields one-turn queries from `question`, every `paraphrases` and every `asr_variants`
     item, each expecting the entry's exact `answer`.
   - Recording tools: use the executor's recorded calls (`FakeApiExecutor.calls`), or a thin wrapper for
     other executors, so calls can be compared exactly.
   - Checks per turn: `flow`, `slots` (expected is a subset of actual, canonical form below), `reply_contains`
     (all), `reply_contains_any` (one), `reply_not_contains` (none), `tool_calls` (exact, ordered; `[]` means none;
     an entry with `error:` expects that error), `actions` (class names, in order). A scenario passes when
     every check of every turn passes.
   - Canonical form for `slots` only: strip whitespace; remove one leading currency symbol from
     `$ € £ ¥ ₩`; remove a trailing currency word (dollar, dollars, usd, 달러, 불, won, krw, 원, yen, jpy, 엔);
     remove commas between digits; compare the result exactly (case-sensitive). The lists are constants in
     one place so they can be changed in one edit.
2. Report: pass rate per capability, domain and language; failing checks with the reason (expected vs actual);
   JSON and Markdown. `python -m voxstage.evaluate run <manager> [--lang en|ko] [--mode clean|noisy] [--out DIR]`
   and `python -m voxstage.evaluate compare a.json b.json` (lists regressions and fixes).
3. `voxstage/ledger.py`: `python -m voxstage.ledger` counts, per step and domain, YAML lines and nodes in
   `flows/`, rules and patterns in `rules/`, interpreter and rule-code lines (files under `voxstage/rules/`),
   and appends a row to `docs/ledger/effort.md` with the commit hash. No column for reactive rules.
4. `NullDM` (always replies with an empty string) and `OracleDM` (given the scenario, replays the expected
   values: a reply containing every `reply_contains` string, or the first `reply_contains_any` option, the
   expected slots, expected tool calls executed through the tool port, expected flow and actions).
   They live in `voxstage/evaluate.py` or `tests/`, whichever keeps the package free of test-only code.

## Done when
- `NullDM` scores 0 percent and `OracleDM` 100 percent on all 144 cases (72 per language), in both modes
  where applicable; the 100 percent also holds for every variant copy.
- Scorer unit tests with hand-built results cover each check type, the canonical form (`"$500"`, `"500 dollars"`,
  `"500달러"`, `"1,250"` pass; `"5000"` and `"five hundred"` fail), and the report round trip and compare tool.
- `python -m unittest discover -s tests` passes. `git diff --stat` touches only new files, `tests/`, and the
  docs named below.
- Docs: add a row for the harness to `docs/design-patterns.md` only if a new pattern was used (say which and why).
  Append the first row to `docs/ledger/effort.md`. Fill in the status line in `queue.md`.

## Stop and report instead of guessing
- Any dataset case that the `OracleDM` cannot satisfy (a spec contradiction): list it in the handoff note.
- A choice not covered by ADR 0008 that changes behaviour: write it as an open question in the handoff note.

## Write-up hook
"Scoring a dialogue system by end state, and why string match lies."
