# Spec R15: interactions and the complexity report (closes S1)

Read first: this file, [queue.md](../queue.md), decision sheet rows R15-1 and R15-2, `docs/dataset-spec.md`,
`docs/ledger/effort.md`, `voxstage/evaluate.py`, `voxstage/ledger.py`.

## Decisions already made (do not reopen)
- R15-1: eight interaction cases, each a pair of earlier features, as en / ko twins, new capability C13: (1) bank
  keypad input during a side question (R3 x R7); (2) bank amount correction, then the transfer confirmation
  (R9 x R7b); (3) bank correction during identity verification (R13 x R9); (4) shop switch to another flow during
  an API failure (R12 x R6); (5) shop return, cancel, then a new return (R8 x R10); (6) telecom several slots with a
  spoken duration (R10 x R11); (7) telecom a "no" at a risky confirmation with a correction (R7b x R9); (8) a policy
  question inside a running flow, then return (R14 x R7). The new cases are an approved dataset change. Expected
  values are written from the decisions, not from what the engine does; failures are findings and are not fixed in
  R15.
- R15-2 (declare S1 finished or continue) is not decided; this item only prepares the evidence.

## Build
1. Capability `C13` in `voxstage/dataset.py` and `docs/dataset-spec.md`; sixteen scenario files
   `domains/<d>/<lang>/scenarios/C13-*.yaml`, ids `<domain>.C13.001` to `.008` (twins share the number).
2. `voxstage/complexity.py`: reads the effort ledger and measures each step's clean-mode pass rate by running the
   harness on the commit that ended the step (a ledger row cannot say it: the ledger was run while the work was
   uncommitted and in a different order than the work, so the end commits are listed in the tool); cost is
   re-measured from the same commit with the current ledger code, because the early ledger rows lack rule-file
   entries and normalize lines (decision R11-5); results kept in `docs/ledger/pass-rates.json`;
   `report` writes `docs/ledger/complexity.md` and `complexity.png` (rules, flow lines and code lines against pass
   rate).
3. `docs/stage-comparison.md`: the S1 row (pass rate per capability, both languages and modes; rules, flow lines
   and code lines; the weaknesses found), with empty S2 and S3 rows for later steps to fill.
4. Ledger rows for R15; whole-suite `compare` before and after.

## Done when
- C13 loads and runs in both languages and modes; NullDM 0 and OracleDM 100 percent still hold with the new cases.
- No earlier case changes result (compare lists none) except the new C13 cases.
- The curve, the report and the S1 row exist, with a findings list: each failing C13 case with the reason.
- Tests: the dataset loader accepts C13; `complexity` parses the ledger and sums per step and language.

## Metrics for the handoff note
C13 pass counts per language and mode with the failing cases and reasons; overall pass counts in both modes; the
curve's end points; lines of the new code.
