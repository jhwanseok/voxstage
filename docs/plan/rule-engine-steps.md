# Rule engine (S1): step-by-step plan

Nothing here is built yet. Each step is implemented only when the owner asks for it
("build R3"). The order below is a proposal; the owner can reorder subject to the dependencies.

## How a step runs

1. **Decision brief.** Before any code, the assistant lists the open decisions of the step with
   options, trade-offs and a recommendation. The owner decides.
2. **Record.** Each decision becomes a record in `docs/decisions/` (decided by, options, reasoning
   in the owner's words where given, public basis). Patterns used go into
   [design-patterns.md](../design-patterns.md).
3. **Build.** Code, domain content for all three domains, and tests, on `dev`.
4. **Measure.** Run the scenario suite, record the numbers in the effort ledger (R0).
5. **Write-up hook.** Each step ends with the one-paragraph finding that can become a post.

A step is done when: its target cases pass in all three domains (or the failures are
documented as findings), tests are green, adding the step's content for the second and third
domain changed no core code (`git diff --stat voxstage/` limited to the step's own additions),
and the ledger row is filled in.

## Fairness rules for the rule baseline (from the plan)

- Build the rules a competent engineer would write for that capability, no more and no less.
  A weak baseline makes the later comparison meaningless.
- Do not tune rules to the exact test wording. Paraphrase and recognition-error variants are the
  held-out part; the authored rules may only use the canonical question and the capability spec.
- A rule added after seeing a failure is recorded in the ledger as a *reactive* rule, separately
  from rules written up front. The share of reactive rules is itself a finding.

## Dependencies

```
R0 ──► R1 ──► R2 ──► R3 ──► R4 ──► R5
                │
                ├──► R6 ──► R7 ──► R8
                ├──► R9 ──► R10
                ├──► R11
                ├──► R12 ──► R13
                └──► R14
                          all ──► R15
```

R0 and R1 come first. R2 (the interpreter) is needed by everything after it. R3 to R14 can be
reordered among themselves when the arrows allow.

---

## R0. Evaluation harness (text mode) and effort ledger

**Goal.** A way to score any dialogue manager on the dataset, and to measure how much effort a
rule base costs. Everything later is judged by it.

**Build.**
- `voxstage/evaluate.py`: runs scenarios against a `DialogueManager` and a `ToolExecutor`.
  - Per scenario: initial state from `setup`, then each turn through `step()`.
  - Input mode: `clean` (the `text`) or `noisy` (the `asr_text` when present).
  - Variants: each variant text is run as an extra copy of that scenario.
  - FAQ cases: every paraphrase and ASR variant is a one-turn query that must return the entry's
    exact answer; an `unanswerable` list (R1) must return the fallback.
- A recording `ToolExecutor` wrapper so tool calls can be compared exactly with `tool_calls`.
- Scorer: per-turn checks for `flow`, `slots` (expected is a subset of actual), the three reply
  checks, `tool_calls` (exact, ordered), `actions`. A scenario passes when every check passes.
- Report: pass rate per capability and domain, list of failing checks with the reason, JSON and
  Markdown output. `compare a.json b.json` lists regressions and fixes (used by R14).
- Effort ledger: `python -m voxstage.ledger` counts, per step and domain, YAML lines and nodes in
  `flows/`, number of rules and patterns, interpreter and rule-code lines, and the share of
  reactive rules; appends a row to `docs/ledger/effort.md`.
- A `NullDM` (answers nothing) and an `OracleDM` (replays the expected values) to prove the
  scorer's floor (0 percent) and ceiling (100 percent).

**Decisions for the owner.**
1. How a manager gets tools and scenario setup: constructor arguments (`tools`, domain pack) with
   `setup` copied into `state.meta`, or passed on every call. Recommendation: constructor plus
   `state.meta`, consistent with the stateless contract.
2. Whether `slots` comparison is exact string match or after light normalisation. Recommendation:
   exact, because normalisation is a capability (C07) being measured.
3. What counts as a *reactive* rule and who labels it. Recommendation: the owner labels it at commit
   time with a tag in the ledger.

**Tests.** Scorer unit tests with hand-built results, `NullDM` = 0 and `OracleDM` = 100 on all 72
cases, report round trip, compare tool.

**Public basis to find.** [τ-bench](https://arxiv.org/abs/2406.12045) scores by end state rather
than wording (already verified); the effort metrics have no public source, so they are validated by
the experiment itself.

**Write-up hook.** "Scoring a dialogue system by end state, and why string match lies."

---

## R1. FAQ with keyword rules (C00, the STT, FAQ, TTS start point without STT and TTS)

**Goal.** The simplest rule engine: question in, verbatim answer out, with a safe fallback.

**Build.**
- `voxstage/domain_pack.py`: loads a domain's FAQ, tools, flows, notices and policy for one language.
- `voxstage/rules/faq.py`: `FaqRuleManager`. Authored patterns per entry in
  `domains/<d>/en/rules/faq_patterns.yaml`: `all_of`, `any_of`, `none_of` word groups, plus
  a priority. Matching on normalised tokens; highest priority then most specific wins; below
  threshold gives the fallback reply and a re-prompt.
- Dataset extension: an `unanswerable` list per `faq.yaml` (about five out-of-scope questions per
  domain) to measure false accepts. Needs the owner's approval of the wording.

**Decisions for the owner.**
1. Pattern language: word groups (as above), regular expressions, or both. Recommendation: word
   groups first; regexes only when a word group cannot express the rule, logged as such.
2. Fallback behaviour: one generic apology, or a counter that escalates to a hand-off after N misses
   (the latter overlaps with R8). Recommendation: generic reply now, escalation in R8.
3. Whether the authored patterns may look at `asr_variants` while writing. Recommendation: no, they are
   held out.

**Cases.** C00 in all three domains: 24 entries, each with its paraphrases and ASR variants, plus
the unanswerable lists.

**Metrics.** Top-1 accuracy on paraphrases, on ASR variants, false-accept rate, patterns per entry,
reactive-rule share.

**Public basis to find.** None for hand-written keyword rules. [BEIR](https://arxiv.org/abs/2104.08663)
supports using BM25 as the baseline once retrieval arrives in S2; that comparison is planned there,
not here.

**Write-up hook.** "A rule-based FAQ: how many keywords until it stops generalising."

---

## R2. Flow interpreter

**Goal.** Realise ADR 0003: domains describe conversations as YAML, one generic interpreter runs
them. After this step the core never changes when a flow is added.

**Build.**
- Flow schema in `domains/<d>/en/flows/*.yaml`: `id`, `triggers` (reusing R1's pattern language),
  and nodes of types `say`, `ask` (slot, prompt, extractor), `call` (tool, args from slots, `on_ok`,
  `on_error`), `branch` (conditions on slots, customer attributes, policy), `goto`, `end`.
- `voxstage/rules/interpreter.py`: `FlowManager`, a `DialogueManager`. State in `DialogueState`
  (`flow_id`, `node_id`, `slots`); templates with `{slot}` and `{result.field}`.
- Slot extractors: `text`, `number`, `choice` (gazetteer). More arrive with R10 and R11.
- The first flows: `balance_inquiry`, `order_status`, `data_usage` (lookup flows), enough for R3, R4.

**Decisions for the owner.**
1. Schema shape: a node list with implicit order, or a state-machine map with explicit transitions.
   The map is more verbose but makes jumps (R6 to R8) explicit.
2. Template language: Python-style `{}` fields only, or a small expression language. Recommendation:
   `{}` fields only; conditions live in `branch` nodes.
3. How node types dispatch: registry of handlers, `match` statement, or a class per node. Affects the
   design-patterns record; the assistant presents the three with a short code sketch.
4. Where validation of a flow happens (load time, with node reachability checks). Recommendation: load time.

**Cases.** Lookup parts of C04 and C08 (R3, R4 finish them).

**Metrics.** Interpreter lines (the baseline for the complexity curve), nodes per flow, lines per
flow, core diff when the second and third domain's first flow is added (target: zero).

**Public basis to find.** [Schema-Guided Dialogue](https://arxiv.org/abs/1909.05855) for declarative
service descriptions (verified). Rasa's documentation on flows is a candidate and must be opened and
read before it is cited.

**Write-up hook.** "A tiny flow interpreter: what the YAML can and cannot say."

---

## R3. Button and DTMF input (C04)

**Goal.** Non-speech input handled deterministically.

**Build.** Node-level input declarations: `accept: {dtmf: {slot, length, pattern}, button: {id → value or flow}}`.
Menu nodes mapping buttons to flows; DTMF validation (length, digits only) with a re-prompt; what to do when
the caller speaks while a keypad answer is expected.

**Decisions for the owner.**
1. Spoken input at a keypad prompt: accept it, ignore it, or re-prompt. Recommendation: accept a spoken
   value through the same extractor, because real callers do it.
2. Invalid keypad input: re-prompt count before escalation. Recommendation: two, then hand off (needs R8).

**Cases.** C04 in three domains.

**Write-up hook.** "The input that cannot be misheard: DTMF as a first-class channel."

---

## R4. Answers from attributes and API results (C08)

**Goal.** Compose a reply from customer attributes and a tool result.

**Build.** `call` node wired to the `ToolExecutor`; attribute access (`customer.tier`) from `state.meta`;
templates over results; speech-friendly formatting of amounts, dates and counts.

**Decisions for the owner.**
1. Number formatting for speech: digits (`$1,250`), words, or both options in the template language.
   Recommendation: a formatter per type (`money`, `date`, `count`) chosen in the template, so the choice is data.
2. Missing attribute: ask the caller, use a default, or fail. Recommendation: fail visibly, never default silently.

**Cases.** C08 (six scenarios), plus the lookup parts of C04.

**Write-up hook.** "Branching on who is asking: attributes in a rule engine."

---

## R5. Condition-specific fixed answers (C09)

**Goal.** Required wording goes out exactly, only when the condition holds.

**Build.** `domains/<d>/en/notices.yaml` (`id`, `text`, `applies_when`) and a `say_notice` node. The
scorer already checks verbatim presence and forbidden phrases.

**Decisions for the owner.**
1. Where notices live: a registry file (recommended) or inline in flows. A registry makes "which notices
   can ever be spoken" auditable.
2. Order when several notices apply, and whether a notice may be interrupted. Recommendation: fixed
   priority list, never interrupted.

**Cases.** C09 (six scenarios).

**Write-up hook.** "Exact words on demand: where rules beat generation."

---

## R6. Scenario switching (C01)

**Goal.** Move from one flow to another when a condition fires.

**Build.** Per-flow `interrupts`: trigger patterns, priority, and guards (for example "not while confirming a
payment"). Switch policy: abandon the old flow or park it (parking is finished in R7). Slot carry-over rules.

**Decisions for the owner.**
1. Abandon versus park on switch. Recommendation: park, so R7 builds on it.
2. Which slots carry over (none, shared names, declared). Recommendation: declared carry-over only.
3. Conflict when two interrupts match. Recommendation: priority, then specificity, logged in `trace`.

**Cases.** C01 in three domains.

**Write-up hook.** "When two intents collide: priorities and guards."

---

## R7. Side question, then return (C02)

**Goal.** Answer a digression without losing the flow.

**Build.** A flow stack in `DialogueState` (park and resume); FAQ interception while inside a flow; re-asking the
pending prompt on return; a depth limit.

**Decisions for the owner.**
1. Which things may interrupt a flow: FAQ only, or also other flows. Recommendation: FAQ now, flows via R6.
2. What happens to a half-filled slot on digression. Recommendation: kept.
3. Stack limit and what is said when exceeded.

**Cases.** C02 in three domains.

**Write-up hook.** "The stack nobody drew: resuming a conversation."

---

## R8. Cancel, back, hand-off (C03)

**Goal.** Global commands that work anywhere.

**Build.** A global command layer ahead of flow handling: `cancel`, `back` (node history in state), `agent`.
`HandOff` actions with a reason; hand-off after repeated failures (counter from R1 and R3).

**Decisions for the owner.**
1. `back` semantics: previous node, or previous question. Recommendation: previous question.
2. When the system volunteers a hand-off (N failures, N corrections). Recommendation: configurable per domain pack.
3. What survives `cancel`: nothing, or customer attributes only.

**Cases.** C03 in three domains.

**Write-up hook.** "Escape hatches: designing for the caller who wants out."

---

## R9. Slot correction after misrecognition (C05)

**Goal.** Notice and repair a wrongly filled slot.

**Build.** Read-back confirmation policy per slot type; correction intents (`no`, `I said ...`, `not X, Y`);
an authored confusion table for number pairs (thirty and thirteen, fifteen and fifty, forty and fourteen);
re-ask limits.

**Decisions for the owner.**
1. When to confirm: every slot, risky slot types only, or only after a flag. In text mode there is no ASR confidence,
   so the choice cannot use one. Recommendation: confirm slot types declared `risky` (amounts, digits).
2. Whether the confusion table is authored by hand or derived. Recommendation: by hand, counted in the ledger.
3. Behaviour when the correction itself looks wrong.

**Cases.** C05 in three domains, noisy mode, with variants.

**Public basis to find.** In-context DST ([Hu et al.](https://arxiv.org/abs/2203.08568), verified) frames DST as the
comparison point for S3; rule-side correction strategies have no source yet, so they are validated by experiment.

**Write-up hook.** "Thirty or thirteen? Repairing what the recogniser got wrong."

---

## R10. Many slots at once, carry-over, references (C06)

**Goal.** Take every slot the caller gave, keep the rest.

**Build.** Run all of a flow's extractors on every utterance, not just the asked one; partial updates that keep other
slots; a minimal reference rule ("it", "that one", "the same") resolving to the last mentioned item.

**Decisions for the owner.**
1. Extraction method: gazetteers and regex, or small pattern grammars. Recommendation: gazetteers plus regex.
2. Which references to support. Recommendation: only the ones the dataset needs, and list the rest as findings.

**Cases.** C06 in three domains.

**Write-up hook.** "Slots that arrive early: the combinatorics of free word order."

---

## R11. Normalisation of numbers, dates and times (C07)

**Goal.** Spoken forms become exact values against a controlled clock.

**Build.** `voxstage/rules/normalize.py`: pure functions (number words, ordinals, day of month, relative dates against
`setup.now`, time windows), table-driven unit tests.

**Decisions for the owner.**
1. Write it or use a library (`dateparser`, `word2number`). A library saves effort but adds dependencies and
   behaviour the repo does not control. Recommendation: write the small subset the dataset needs, note what a
   library would add.
2. Ambiguity policy for dates such as "next Tuesday". Recommendation: ask rather than guess.

**Cases.** C07 in three domains, plus a table of normalisation unit cases.

**Write-up hook.** "Twenty five hundred and the fifteenth of next month."

---

## R12. API failure and delay fallback (C10)

**Goal.** Never invent an answer when the tool fails.

**Build.** Error policy on `call` nodes: retry once, fallback reply, hand-off after N failures; a simulated-delay
option in the fake API.

**Decisions for the owner.**
1. Retry count and whether the caller is told. Recommendation: retry once silently, then tell.
2. Fallback wording: generic or per tool.

**Cases.** C10 in three domains.

**Write-up hook.** "When the backend is down: fallback paths a rule engine must enumerate."

---

## R13. Identity gate (C11)

**Goal.** No protected information before verification, and no tool call that would leak it.

**Build.** `requires: verified` on flows or nodes; a verification flow with a failure counter and lockout; a state flag;
a check that blocks tool calls before verification.

**Decisions for the owner.**
1. Granularity: per flow, per node, or per tool. Recommendation: per tool, because that is where leakage happens.
2. Lockout rule and what is said.

**Cases.** C11 (six scenarios).

**Write-up hook.** "Gating by tool, not by flow."

---

## R14. Policy change (C12)

**Goal.** Measure what a business-rule change costs.

**Build.** `domains/<d>/en/policy.yaml` with values referenced from replies; `compare` from R0 run before and after
a change; a second run where the same value is hard-coded in several replies, to show the difference.

**Decisions for the owner.**
1. Whether to include the hard-coded variant as a deliberate counter-example. Recommendation: yes, it is the point.
2. Which change to simulate beyond the shipped v1 to v2 pairs.

**Cases.** C12 (six scenarios) plus regression comparison over the whole suite.

**Write-up hook.** "One line changed: how far does a policy edit reach?"

---

## R15. Interactions and the complexity report

**Goal.** Show where rule complexity actually explodes, and close S1.

**Build.**
- Interaction cases (about eight, across domains, needing the owner's approval): keypad input during a digression,
  correction during identity verification, switch during an API failure, and so on.
- The complexity curve: cumulative nodes, rules and lines against pass rate, step by step, from the ledger.
- The S1 row of the stage comparison table, ready for S3 to fill in beside it.

**Decisions for the owner.**
1. Which interactions to include. The assistant proposes a list with the reasoning for each.
2. Whether S1 is declared finished or reactive rules continue.

**Write-up hook.** "Rule explosion: it is not the features, it is the pairs."

---

## Separate track A1. Audio path (needs the English vendor decision)

Connect ASR, the rule manager and TTS: speech in, an `Utterance` out of the recogniser, the manager's reply
through TTS, with latency events as before. Not scheduled until the English ASR and TTS models are chosen
(see [0006](../decisions/0006-english-first.md)). It can start right after R1 if the owner wants a spoken demo early.

## Suggested pace

One write-up per one or two steps, about one a week as a goal, not a rule.

| Weeks | Steps | Likely post |
|---|---|---|
| 1 | R0 | Scoring by end state |
| 2 | R1 | Rule-based FAQ limits |
| 3 | R2 | Flow interpreter |
| 4 | R3, R4 | DTMF and attribute answers |
| 5 | R5 | Verbatim answers |
| 6 to 7 | R6 to R8 | Switching, resuming, escaping |
| 8 to 9 | R9, R10 | Correction and multi-slot |
| 10 | R11 | Normalisation |
| 11 | R12, R13 | Failure and gating |
| 12 | R14 | Policy change |
| 13 | R15 | Rule explosion |
