# Spec R14: policy change (C12)

Read first: this file, [queue.md](../queue.md), decision sheet rows R14-1 to R14-3, R4-1, R4-2,
`docs/flow-spec.md`, `voxstage/evaluate.py` (`compare`), `voxstage/ledger.py`, and the C12 scenario files.

## Decisions already made (do not reopen)
- R14-1: the hard-coded variant is included as a deliberate counter-example.
- R14-2: the change simulated beyond the shipped v1 to v2 pairs is one threshold in the shop domain, the
  free-shipping threshold, compared with the hard-coded variant using the same value. Other kinds of change
  (wording policy, added conditions) go to the backlog.
- R14-3: one small flow per policy question (trigger, `say` with `{policy.<key>}` through the R4 formatters, `end`);
  FAQ answers stay fixed text read as written. A missing policy value apologises and hands off (R4-2).

## Build
1. Policy flows (twins, en and ko), no new engine code:
   - bank `free_transfers`: `policy.free_transfers_per_month` (`count`);
   - shop `free_shipping`: `policy.free_shipping_threshold` (`money('USD')`);
   - telecom `grace_period`: `policy.late_payment_grace_days` (`count`).
2. Shop only, for the R14-2 comparison: two more flows that say the same threshold in other words
   (`free_shipping_offer`: "do you offer free shipping", `free_shipping_how`: "how do I get free shipping"), so the
   value is spoken in three replies. In the referenced pack each reads `policy.free_shipping_threshold`.
3. Hard-coded variant, kept as files (R14-1; the owner chose files over a generated copy on 2026-10-27):
   `domains_variants/hardcoded/shop/{en,ko}/flows/` holds the same three flows with the v1 value (50 dollars) written
   into the text. An overlay: only these files differ from `domains/`.
4. `voxstage/policy_impact.py` (`python -m voxstage.policy_impact`): for the referenced pack and the
   hard-coded overlay it reports the C12 passes under v1 and v2, the flow files and lines a move to v2 must edit, and, for the
   R14-2 threshold change (default 50 to 100) after the edit the C12 case points to (the minimum-order reply), how
   many of the three replies still say the old value.
5. Ledger rows for R14 (`python -m voxstage.ledger R14`); `compare` of the whole suite before and after, in both
   modes and languages.
6. `docs/flow-spec.md`: a short section "Policy values (R14)".

## Done when
- C12 base scenarios pass in all three domains and both languages, clean mode (v1 and v2).
- Earlier results hold in both modes; every regression is listed. NullDM 0 and OracleDM 100.
- Tests: each policy flow answers from the policy value (two values each); a missing value apologises and hands off;
  the hard-coded variant ignores `setup.policy`; `policy_impact` counts for the 50 to 100 change; the policy flows'
  triggers do not take over other flows' questions.

## Metrics for the handoff note
C12 pass counts per domain and language; overall pass counts in both modes; lines and nodes of the new flows;
edit places and stale replies for both variants after the 50 to 100 change.
