# Spec R8: cancel, back, hand-off (C03)

Read first: this file, [queue.md](../queue.md), decision sheet rows R8-1 to R8-6, R6-1 to R6-7, R7-1 to R7-12,
`docs/flow-spec.md`, `voxstage/domain_pack.py`, `voxstage/rules/flows.py`, `voxstage/rules/interpreter.py`, the C03
scenario files, and the C01 shop scenarios (the `cancel` clash).

## Decisions already made (do not reopen)
- R8-1: `back` asks the previous answered `ask` again (say, branch and call nodes are skipped); the earlier answer
  stays until a new one comes; the question is asked even though its slot is filled; at the first question it is
  asked again; a tool call already made is not undone. The asked questions are kept in `state.meta`.
- R8-2: no new escalation counter; R8 adds only the hand-off the caller asks for.
- R8-3: `cancel` keeps what came with the request (`customer`, `policy`, other setup values in `meta`) and clears
  slots, the flow, every parked flow, the question history, the last `result` and the counters. `flow_id` becomes
  the reserved name `main_menu`; no flow file may be called `main_menu`. Reply: `command.cancelled`, also outside a
  flow.
- R8-4: `rules/commands.yaml` per domain and language with exactly `cancel`, `back`, `agent` in the pattern language;
  `agent` returns `HandOff("caller_request")` with `command.agent` and drops parked flows; `back` outside a flow says
  `flow.no_flow`. The words are written by this session (it has read the C03 variants).
- R8-5: commands come first in every state, also at a `confirm`: commands, then a button switch, then `interrupts:`,
  then answer / FAQ. The shop `cancel` command has `none_of` words for an order reference (en `order`, `cancel it`;
  ko 주문, 그거).
- R8-6: tool `update_address` (`[order_id, address]`, default `{status: updated}`, `risky: true`) and flow
  `change_address` (order number, new address, confirm, call, done or apology).

## Build
1. `rules/commands.yaml` loader in `voxstage/domain_pack.py` (exactly the three names, each a pattern; required for
   every pack with a `rules/config.yaml`); registry keys `command.cancelled` and `command.agent` become required.
   The flow loader rejects a flow id `main_menu`.
2. Interpreter, command layer at the top of `respond` (utterances only; keypad and buttons are not commands):
   - `cancel`: the R8-3 state; `trace["command"] = "cancel"`, with `parked_dropped` when parked flows existed.
   - `agent`: `command.agent` and `HandOff("caller_request")`; parked flows dropped; flow and slots stay.
   - `back`: at a waiting `ask` or `confirm`, the newest entry of `state.meta["asked"]` is asked again (its node
     becomes the current node; slots unchanged); with an empty history the current question is asked again; outside
     a flow, `flow.no_flow`. `trace["back_to"]` names the node.
   - The history: the node id of an `ask` is appended when it is answered; a flow that starts (trigger, button,
     switch) starts with an empty history; a parked entry keeps its history and a resumed flow gets it back.
   - The command matcher uses the same priority-then-specificity rule as triggers; `trace["command_match"]` shows it.
3. Content (twins in all three domains): `commands.yaml`; `command.cancelled` and `command.agent` wording in every
   `notices.yaml`; shop `update_address` in `tools.yaml` and the `change_address` flow.
4. `docs/flow-spec.md`: a section "Global commands (R8)".

## Done when
- C03 base scenarios pass in all three domains and both languages, clean mode; variants and noisy mode are reported.
- Earlier results hold except where a command takes over on purpose; every regression is listed in the handoff note
  (expected: shop C01 variants that cancel without an order reference, such as "I changed my mind I want to cancel").
  NullDM 0 and OracleDM 100 percent.
- Tests: commands.yaml validation; required wording; `main_menu` flow id rejected; cancel clears what R8-3 says and
  keeps request meta; cancel at a confirm calls no tool; agent hands off and drops parked flows; back to the previous
  question with the slot kept and the question asked although filled; back at the first question; back outside a
  flow; history across a switch and a resume; commands before interrupts; the shop `cancel` clash both ways.

## Metrics for the handoff note
C03 pass counts per domain and language (base, variants, noisy); overall pass counts; number of command patterns;
interpreter lines; `change_address` lines and nodes; earlier cases taken over by commands.
