# Stage comparison

The same cases run against every stage, so the stages can be put side by side
([ADR 0005](decisions/0005-dataset-first-development.md)). S1 is the rule engine (R0 to R15). The S2 and S3 rows are
left empty for the later stages to fill in beside it. Rates are cases passed out of cases in the capability, from
`python -m voxstage.evaluate run voxstage.rules.interpreter:default_factory`, measured at the end of R15.

S1 was declared finished on 2026-10-28 (decision R15-2): no more rules are added; the findings below are carried into the S3 comparison.

## S1 row: pass rate per capability

| Capability | en clean | en noisy | ko clean | ko noisy | S2 | S3 |
|---|---|---|---|---|---|---|
| C00 FAQ answer | 89 / 144 | 89 / 144 | 86 / 149 | 86 / 149 | | |
| C01 Scenario switch | 10 / 12 | 10 / 12 | 7 / 12 | 7 / 12 | | |
| C02 Return after a side question | 5 / 6 | 5 / 6 | 4 / 6 | 4 / 6 | | |
| C03 Cancel, back, hand off | 18 / 18 | 18 / 18 | 14 / 18 | 14 / 18 | | |
| C04 Button / DTMF input | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | | |
| C05 Slot re-fill after misrecognition | 0 / 12 | 11 / 12 | 0 / 12 | 6 / 12 | | |
| C06 Multiple slots, references | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | | |
| C07 Number, date, time | 4 / 9 | 4 / 9 | 5 / 10 | 5 / 10 | | |
| C08 Answer from attributes and API | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 | | |
| C09 Condition-specific fixed answer | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 | | |
| C10 API failure or delay | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | | |
| C11 Identity gate | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 | | |
| C12 Policy change | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 | | |
| C13 Interactions of two features | 4 / 8 | 6 / 8 | 4 / 8 | 6 / 8 | | |
| **Overall** | **163 / 242** | **176 / 242** | **153 / 248** | **161 / 248** | | |

NullDM scores 0 percent and OracleDM 100 percent in both languages. C05 in clean mode is 0 by construction: clean mode
feeds the true text, so there is no recognition error to correct; the noisy column is the one that measures it.

## S1 row: cost

See [ledger/complexity.md](ledger/complexity.md) and the figure [ledger/complexity.png](ledger/complexity.png):
cumulative rules, flow lines and code lines against the pass rate of each step's own dataset.

## S1 row: what the rules do not handle (findings)

| Where | What happens | Why the rules cannot do it |
|---|---|---|
| C13 bank 003 (R13 x R9) | A corrected account number said while the PIN is asked is not taken; the old digits are used and verification fails. | Only slots on the read-back list can be corrected (R9-1). The account digits are a keypad slot, so a spoken correction is not an answer to the PIN question. |
| C13 shop 008 (R14 x R7) | A policy question inside a running return flow is treated as a bad answer to the order-number question. | Policy replies are flows (R14-3); inside a flow only an FAQ match is a side question (R7-1). The same words work outside a flow. |
| C13 bank 002 and telecom 007, clean mode | The correction has nothing to correct. | Clean mode has no recognition error; both pass in noisy mode. |
| C05 Korean telecom (R9-6) | Kiwi drops 기가 after a misheard number. | Analysis broken by recognition errors is measured, not hidden (ADR 0011). |
| C02 Korean bank (R7-9) | Kiwi drops the dependent noun 시. | Pattern words that cannot be tokens never match. |
| C07 | Dates meant as past are read as future (R11-6). | A per-slot direction is backlog D5. |
