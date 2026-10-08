# Run queue

Decisions are made in the evening, in conversation with the owner. Building happens during the day without the
owner, one queue item per run, from the spec file of that item. Nothing here is built by guessing: an item is
`ready` only when every decision it depends on is recorded in `docs/decisions/`.

| # | Item | Spec | Depends on | Status | Handoff note |
|---|---|---|---|---|---|
| 1 | R0 evaluation harness and ledger | [R0](specs/R0-evaluation-harness.md) | none | done | Built `voxstage/evaluate.py`, `reference_managers.py`, `ledger.py`; `initial_state(session_id, setup)` now copies setup into `meta`. NullDM scores 0 and OracleDM 100 percent in both languages and both modes (en 234 cases, ko 240 cases including variant copies and every FAQ query; 72 base cases per language). Tests: 56 pass. Open: the plan counted 144 cases in total; the harness counts 72 base per language plus expansions, as the spec said. |
| 2 | R1 FAQ rule manager (English and Korean) | [R1](specs/R1-faq-rule-manager.md) | R0 | ready | |
| 3 | R2 flow interpreter | [R2](specs/R2-flow-interpreter.md) | R1 | ready | |
| 4 | R3 button and DTMF | not written | R2 | needs decisions (decision sheet R3-1, R3-2) | |
| 5 | R4 attribute and API answers | not written | R2 | needs decisions (R4-1, R4-2) | |
| 6 | R5 fixed notices | not written | R2 | needs decisions (R5-1, R5-2) | |

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
