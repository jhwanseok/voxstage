# Spec R12: API failure and delay fallback (C10)

Read first: this file, [queue.md](../queue.md), decision sheet rows R12-1 to R12-5, R7-12, R13-1 to R13-3,
`docs/flow-spec.md`, `voxstage/tools.py`, `voxstage/rules/flows.py`, `voxstage/rules/interpreter.py`,
`voxstage/domain_pack.py`, and the C10 scenario files.

## Decisions already made (do not reopen)
- R12-1: a tool may declare `retry: 1`; only a `timeout` is retried, once, silently; not_found and
  invalid_credentials are not retried; a risky tool cannot declare `retry` (load check). C10 cases expect the
  retried call as a second record (a dataset exception, listed in the handoff note).
- R12-2: the specific wording stays in the flows; `on_error` becomes optional; a `call` without it says
  `call.failed` and ends the flow.
- R12-3: a `timeout` of a risky tool says `call.unconfirmed` and returns `HandOff("outcome_unknown")`, before the
  flow's `on_error`; other errors of a risky tool go to `on_error`.
- R12-4: `rules/config.yaml` `tools: {max_failures: 2, on_exceed: handoff}`; system errors (`timeout`, after the
  retry) count over the call; at the limit `call.exceed` replaces the flow's failure wording and the call is handed
  off (`HandOff("tool_failed")` or `EndCall`); not_found and invalid_credentials are not counted.
- R12-5: a fake-API rule may declare `delay_ms` (recorded, not waited for); `tools: {timeout_ms: 5000}`; a slower
  answer is a `timeout` for the engine. Filler speech waits for the voice pipeline; delay cases are backlog D7.

## Build
1. Fake API (`voxstage/tools.py`): tool key `retry` (0 or 1; not with `risky: true`); rule and default key
   `delay_ms` (integer >= 0); `ToolResult.delay_ms` (0 when not declared).
2. Engine (`interpreter.py`, the `call` handler):
   - an answer with `delay_ms` above `timeout_ms` is a `timeout` (its data is dropped; `trace["calls"]` keeps
     `delay_ms`);
   - a `timeout` of a tool with `retry: 1` is called once more (both calls recorded);
   - after that, a `timeout` (a system error): a risky tool ends as R12-3; otherwise the call's failures
     (`meta["tool_failures"]`) count one more and at the limit end as R12-4; below the limit the flow goes to
     `on_error`, or says `call.failed` and ends when there is none;
   - other errors go to `on_error` (or `call.failed` and the end) and are not counted;
   - the verifying tool (R13): a `timeout` is not a failed check (no count towards the lockout); it says
     `call.failed` and ends the check, dropping the stopped flow, unless the tool-failure limit is reached first.
   `trace["call_policy"]` says what happened (retried, unconfirmed, exceeded, default wording).
   `tool_failures` belongs to the call and survives `cancel`.
3. Flows (`flows.py`): `on_error` optional on `call` nodes.
4. Config and wording (`domain_pack.py`): `tools: {max_failures: 2, on_exceed: handoff, timeout_ms: 5000}`
   (validated like `correction`); new required wording keys `call.failed`, `call.unconfirmed`, `call.exceed`.
5. Content: `retry: 1` on the lookup tools (`get_*`) of the three domains; the three wordings in the six packs; the
   `tools` block in the six configs; the six C10 scenario files expect the retried call.
6. `docs/flow-spec.md`: a section "Tool failures and delays (R12)".

## Done when
- C10 base scenarios pass in all three domains and both languages, clean and noisy.
- Earlier results hold in both modes; every regression is listed in the handoff note. NullDM 0 and OracleDM 100.
- Tests: retry once on timeout and not on not_found; a retry that succeeds; load errors (`retry` on a risky tool, bad
  `retry`, bad `delay_ms`); a delay over and under `timeout_ms`; a risky timeout hands off with `call.unconfirmed`
  and a clear risky refusal goes to `on_error`; the failure limit across two flows; not_found not counted; a call
  without `on_error`; a verifying-tool timeout is not a failed check; config validation; the wording keys.

## Metrics for the handoff note
C10 pass counts per domain and language in both modes; overall pass counts in both modes; interpreter lines;
changed scenario files; tools with `retry`.
