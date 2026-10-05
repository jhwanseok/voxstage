# Spec R1: FAQ with keyword rules (C00)

Read first: this file, [queue.md](../queue.md), ADR 0009, `voxstage/evaluate.py` (from R0),
`voxstage/dialogue.py`, `voxstage/dataset.py`. Do not read other plan files.

## Goal
Question in, verbatim answer out, with a configurable escalation after repeated misses. English only.

## Decisions already made (do not reopen)
ADR 0009. Word groups first; regexes only where a word group cannot express the rule, logged; both
`paraphrases` and `asr_variants` are held out; escalate after N consecutive misses, N and the action
(hand off or end call) configurable. Korean rules are not part of this step.

## The held-out rule (read carefully)
Whoever writes `rules/faq_patterns.yaml` may read only each entry's `id`, `question` and `answer`.
Do not open `paraphrases`, `asr_variants`, the scenario files' `variants`, or `asr_text`. Step 1 below
provides a command that prints that view; use only that command to look at the FAQ.
Do the pattern writing before running the evaluation. After the first evaluation you may read failures; a
change made after that is allowed, but it must come from the capability spec (what a competent engineer
would add), not from copying failing wording. Note in the handoff how many patterns changed after the first run.

## Build
1. `python -m voxstage.dataset authoring-view <domain> <lang>`: prints id, question, answer per FAQ entry and
   nothing else. Add it with a test that the output contains no paraphrase or ASR variant text.
2. `voxstage/domain_pack.py`: `DomainPack.load(domain, lang)` bundling FAQ, tools spec path, rules config,
   and (later) flows, notices and policy. Missing optional parts are `None`.
3. `voxstage/rules/faq.py`: `FaqRuleManager(DialogueManager)`. Input handling: `Utterance` only here; other input
   kinds return the fallback path and are noted in the trace. Tokenise by lowercasing and stripping punctuation.
   Each entry has `all_of`, `any_of`, `none_of` (lists of words or word lists for synonyms) and `priority`. An
   entry matches when all `all_of` groups are present, at least one `any_of` word is present (if the list is
   non-empty), and no `none_of` word is present. Highest priority wins, then the most specific (more matched
   words), then file order; ties are written to `trace`. No match: the fallback reply and the miss counter.
4. Rules config `domains/<d>/en/rules/config.yaml`:
   `fallback: {max_misses: 3, on_exceed: handoff | end_call, reply: ..., exceed_reply: ...}`. The consecutive-miss
   counter lives in `state.meta["faq_misses"]` and resets on a match. At `max_misses` the manager returns
   `exceed_reply` with `HandOff("no_match")` or `EndCall()`. Validate the config at load time.
5. `domains/{bank,shop,telecom}/en/rules/faq_patterns.yaml`: one entry per FAQ entry (8 each), plus the config.
6. Dataset extension (draft, unreviewed): `domains/<d>/en/faq_unanswerable.yaml` with five out-of-scope
   questions per domain that must hit the fallback, first line `status: draft`. The loader accepts the file;
   the report prints the false-accept rate on it and marks it "draft, not reviewed by the owner".

## Metrics (write into the run report and the ledger row)
Top-1 accuracy on paraphrases and on ASR variants; false-accept rate on the unanswerable draft; patterns per
entry; number of regex rules; patterns changed after the first run.

## Done when
- C00 passes for the canonical question in all three domains (clean mode); the held-out accuracies are
  reported, not required to be high. Failures are findings, not bugs to be tuned away.
- Tests: tokeniser, matching and priority, config validation, fallback counter (N = 2 and N = 3, both actions),
  authoring view hides held-out text, loader accepts the unanswerable draft.
- `NullDM` and `OracleDM` results from R0 unchanged. All tests pass. Ledger row appended.
- Adding the shop and telecom packs changed no code outside the step's own new files.

## Stop and report
- Nothing in this step needs the owner. If the held-out rule would be broken (for instance a test needs
  the paraphrases), stop that part and note it.

## Write-up hook
"A rule-based FAQ: how many keywords until it stops generalising."
