# Spec R13: identity gate (C11)

Read first: this file, [queue.md](../queue.md), decision sheet rows R13-1 to R13-3, R3-1, R6-2, R7-12, R8-3,
`docs/flow-spec.md`, `voxstage/tools.py`, `voxstage/rules/flows.py`, `voxstage/rules/interpreter.py`,
`voxstage/domain_pack.py`, the C11 scenario files and the bank and shop C04 and C10 scenario files.

## Decisions already made (do not reopen)
- R13-1: the gate is per tool: a tool in `tools.yaml` may declare `requires: verified`; the engine refuses such a
  call before verification in any flow and runs the verification steps first.
- R13-2: after the allowed number of failed attempts the caller is locked out for the rest of the call (no protected
  tool is called again) and handed off (`HandOff("verification_failed")`); neutral wording that never says which
  part was wrong; a pass holds for the rest of the call. `rules/config.yaml` gets `verification: {max_attempts: 3,
  on_exceed: handoff}` as the domain default; a flow may declare `verification: {max_attempts: N}`, which overrides
  the default while that flow runs.
- R13-3: bank and shop C04 and C10 (en and ko) get a verification turn after the account or order number; for C10
  the fake API gets a passing credential for the timeout account / order. The verification steps are declared per
  domain (which slots are asked, which tool checks them), not hard-coded to a PIN; other sign-in methods are D6.

## Build
1. Tool keys (`voxstage/tools.py`, `voxstage/rules/flows.py`):
   - `requires: verified` marks a protected tool (bank `get_balance`, shop `get_order_status`, telecom `get_bill`);
   - `verifies: true` marks the tool that checks the caller (`verify_identity` in each domain); exactly one per
     domain when any tool is protected; a tool cannot have both keys.
2. Verification flow (`flows.py`): a flow file may declare `role: verification`; it has no `triggers`, `buttons`,
   `interrupts` or `captures` (it cannot be started by the caller), may declare `carry` (the identifier slots it
   takes from the gated flow, for example `account_last4`), and must call the `verifies` tool. Load checks: exactly
   one verification flow per pack when any tool is protected; a protected tool is never called inside it.
3. Prefill from the caller's record (`flows.py`, `interpreter.py`): a flow may declare `prefill: {<slot>:
   customer.<attribute>}`; when the flow starts, a slot that is still empty takes the attribute when the request
   carries it (C11: the caller's account is known, so it is not asked). Captured words win over a prefill.
4. The gate (`interpreter.py`), at a `call` node of a protected tool:
   - verified in this call (`meta["verified"]`): the call runs as before;
   - locked (`meta["verification_locked"]`): no call; the reply is `verify.locked` with `HandOff("verification_failed")`;
   - otherwise: no call; the running flow is kept in `meta["gated"]` (flow, node, slots, asked, form state, its
     attempt limit) and the verification flow starts with the `carry` slots of the gated flow and its own prefill;
     `trace["gate"]` names the tool.
   At the call of the `verifies` tool:
   - ok: `meta["verified"] = True`; when the verification flow ends, the gated flow continues at its call node in
     the same turn (so one turn holds `verify_identity` and then the protected call);
   - error: the attempt counts in `meta["verify_failures"]`; the slots the verification flow asked are emptied (its
     questions are asked again); at the limit (the gated flow's `verification.max_attempts`, else the config default)
     the call is locked: the reply is `verify.locked`, the action `HandOff("verification_failed")` (or `EndCall`),
     the gated and parked flows are dropped; below the limit the flow goes on to its `on_error` node.
   `cancel` drops `meta["gated"]` but keeps `verified`, `verification_locked` and the failure count (they belong to
   the call, not to the talk). Commands, side questions, back and switching at the verification questions follow
   the `ask` rules.
5. Config and wording (`domain_pack.py`): `verification: {max_attempts, on_exceed}` in `rules/config.yaml` (validated
   like `correction`; `max_attempts` at least 1; on_exceed `handoff` or `end_call`); new required wording key
   `verify.locked`. A flow's own `verification: {max_attempts: N}` is validated in `flows.py`.
6. Content (twins):
   - `tools.yaml`: the keys of item 1; extra passing credentials for C10 (bank `0000` + PIN `2468`, shop `9999` +
     ZIP `12345`); `pin` joins the keypad-only slots of bank and telecom (a secret is never taken by voice, R3-1);
   - a verification flow per domain and language (bank and telecom: PIN; shop: ZIP code), failure wording that does
     not say which part was wrong ("The details you entered don't match. Please try again.");
   - `prefill` of the identifier in bank `balance_inquiry`, shop `order_status` and telecom `bill_inquiry`;
   - telecom `bill_inquiry` (new): line from the caller's record or asked, `get_bill`, the amount and due date;
   - the eight C04 / C10 scenario files (R13-3).
7. `docs/flow-spec.md`: a section "Identity gate (R13)".

## Done when
- C11 base scenarios pass in all three domains and both languages, clean mode; C04 and C10 (changed) still pass.
- Earlier results hold in both modes; every regression is listed in the handoff note. NullDM 0 and OracleDM 100.
- Tests: no protected call before verification (from any flow); pass, then the protected call in the same turn;
  wrong credentials with neutral wording; lockout at the limit with a hand-off and no later protected call; a flow's
  own limit overriding the default; the slot is asked again after a failure; prefill from `customer` and a capture
  winning over it; cancel keeps `verified`; load errors (two verification flows, missing verifies tool, a protected
  call inside the verification flow, both keys on one tool, a trigger on the verification flow, bad `verification`
  config).

## Metrics for the handoff note
C11 pass counts (base, variants, noisy) per domain and language; overall pass counts in both modes; lines and nodes
of the verification flows; interpreter lines; changed scenario files.
