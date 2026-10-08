# Run queue

Decisions are made in the evening, in conversation with the owner. Building happens during the day without the
owner, one queue item per run, from the spec file of that item. Nothing here is built by guessing: an item is
`ready` only when every decision it depends on is recorded in `docs/decisions/`.

| # | Item | Spec | Depends on | Status | Handoff note |
|---|---|---|---|---|---|
| 1 | R0 evaluation harness and ledger | [R0](specs/R0-evaluation-harness.md) | none | done | Built `voxstage/evaluate.py`, `reference_managers.py`, `ledger.py`; `initial_state(session_id, setup)` now copies setup into `meta`. NullDM scores 0 and OracleDM 100 percent in both languages and both modes (en 234 cases, ko 240 cases including variant copies and every FAQ query; 72 base cases per language). Tests: 56 pass. Open: the plan counted 144 cases in total; the harness counts 72 base per language plus expansions, as the spec said. |
| 2 | R1 FAQ rule manager (English and Korean) | [R1](specs/R1-faq-rule-manager.md) | R0 | done | Built `voxstage/rules/{tokenize,faq}.py`, `domain_pack.py`, authoring view, unanswerable drafts, fallback with configurable N and action. Patterns were written by three fresh sessions (one per domain, both languages) that read only the authoring view; 0 regex rules, 0 patterns changed after the first run (nothing was tuned). **First run, clean mode, FAQ queries:** canonical question 24/24 in both languages. Paraphrases en bank 17/24, shop 16/24, telecom 21/24 (54/72, 75.0%); ko bank 15/24, shop 13/24, telecom 17/24 (45/72, 62.5%). ASR variants en 9/16, 7/16, 6/16 (22/48, 45.8%); ko 9/16, 12/21, 9/16 (30/53, 56.6%). False accepts on the draft unanswerable lists 0/15 in both languages. Patterns per entry 1 (8 per pack, 48 in total). Tests: 78 pass (Korean tests need `pip install -e .[ko]`). Open: the unanswerable drafts are unreviewed; the Korean FAQ has five more ASR variants than the English one (53 vs 48), so source totals differ by language; the agents flagged under-covered phrasings (daily limit without the word limit, bare 'track it', outage versus roaming ambiguity). Findings, not bugs: they are the write-up. |
| 3 | R2 flow interpreter | [R2](specs/R2-flow-interpreter.md) | R1 | done | Built `voxstage/rules/{expr,flows,interpreter,matching}.py`, six lookup flows (balance_inquiry, order_status, data_usage; English and Korean twins), `docs/flow-spec.md`. **Metrics:** interpreter code lines 521 (interpreter.py, flows.py, expr.py), other rule code 164; flow YAML lines 9 / 18 / 9 per flow (bank / shop / telecom) with 5 / 8 / 5 nodes; 26 template and branch expressions using 6 operator nodes in total. Tests: 104 pass. **Core diff:** all three flows were written in one pass after the interpreter, so the intended check (adding shop and telecom changed no core file) was not run in order; the only core edit after the flows existed was in `expr.py` (a bare function name such as `len` is now rejected at load), found by a test, and no node type, schema or loop code changed when the shop branch flow and the telecom flow were added. **Scenarios:** the lookup scenarios of C04 and C10 start with a button (R3), so none of the 72 base scenarios passes yet; the flows' lookup turns are covered by unit tests with the scenario's expected phrases (`last four digits`, `order number`, `배송 중`, `12GB`, failure wording without invented numbers). **Findings:** combined with the FAQ rules (flows first), the flow triggers take over held-out FAQ queries that mention the same words: en `shop.faq.shipping_time#paraphrase.1`, `shop.faq.track_order#paraphrase.1`, `telecom.faq.check_usage#paraphrase.1`; ko the same three plus `shop.faq.track_order#asr_variant.5` and `telecom.faq.check_usage#paraphrase.2`. They were not tuned away: how-to questions versus lookups is the ambiguity the write-up is about. The `data_usage` triggers were narrowed once after a test showed the canonical FAQ question `How do I check my data usage` starting the flow (canonical text only). Deviations from the spec: list and tuple literals are allowed in expressions (needed for `in`); `end` nodes keep `flow_id` and set `node_id` to the end node, so a finished flow is recognised by its node type. Open: R3 will need `ask` to accept button-started flows; flow triggers were written by the same session that had seen the datasets earlier, so they carry no held-out guarantee (R2 has no held-out metric). |
| 4 | R3 button and DTMF | [R3](specs/R3-button-dtmf.md) | R2 | ready | |
| 5 | R4 attribute and API answers | [R4](specs/R4-attributes-and-api.md) | R2 | ready | |
| 6 | R5 fixed notices | [R5](specs/R5-notices-registry.md) | R2 | ready | |

Statuses: `needs decisions` -> `ready` -> `in progress` -> `done` | `blocked`.
Estimated size is one run per item; a spec that does not fit one usage window is split before it is marked `ready`.

## Run protocol (every run follows this, and nothing else)

1. Work in the repo on branch `dev`. Never push to `main`. Never merge.
2. Open this file. Take the first item with status `ready` whose dependencies are `done`. Set it to `in progress`
   and commit that change. If there is none, stop and say so.
3. Read the item's spec and the files it names, nothing more. Do not read the Korean or English FAQ text beyond
   what the spec allows (R1 held-out rule).
4. Do not make decisions. If something is not covered by a recorded decision or by the spec, do the safest
   reading, and write the question into the handoff note. Never edit an accepted ADR; add a new one only if the
   spec says so.
5. Build in the order of the spec. After each numbered build item, run `python -m unittest discover -s tests`
   and commit to a branch named `wip/<item>` and push it, so a usage limit cannot lose work.
6. When the "Done when" list is satisfied and tests pass: merge the work into `dev` (fast-forward or a plain
   merge), push `dev`, set the item to `done`, fill the handoff note (what was built, numbers from the metrics
   list, open questions, any failures that are findings), and commit and push.
7. If tests cannot be made to pass, leave the code on `wip/<item>`, set the item to `blocked`, and write why and
   what was tried. Do not start the next item in the same run.
8. Commits are authored as `Jeong Hwanseok <jhwanseok.work@gmail.com>` with no co-author trailer and no session
   line (pass `-c user.name=... -c user.email=...`). One item per run.

## Prompt to start a run

"Run the next item of docs/plan/queue.md following its run protocol."
