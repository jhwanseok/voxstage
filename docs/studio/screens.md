# Studio screens

React, TypeScript, Vite; flow editor on React Flow (`@xyflow/react`). Server state through the API in
[api.md](api.md); a bot switcher (domain and language, e.g. `bank-en`) sits in the top bar of every screen, together with the draft status
(`valid` / `has errors` / `unpublished changes`) and the **Publish** button.

## Map

| # | Screen | Stage |
|---|---|---|
| 1 | Domains and import | ST1 |
| 2 | FAQ list and form | ST1 |
| 3 | Tools list and form | ST1 |
| 4 | Flow list | ST1 |
| 5 | Flow viewer (read-only graph) | ST1 |
| 6 | Flow editor (same screen, editing on) | ST2 |
| 7 | Validation panel | ST2 (a plain list in ST1) |
| 8 | Publish dialog, history, diff, rollback | ST2 |
| 9 | Notices and wording | ST3 |
| 10 | Settings (policy, config, confirm words, commands, corrections) | ST3 |
| 11 | Preview chat | ST3 |

## 1. Domains and import

A card per bot, grouped by domain: language, counts (FAQ, flows), draft status, last publication; the domain's shared assets (tools) are listed once per domain. **New bot** creates a bot for a domain and language (empty or copied from a sibling). **Import** opens a dialog:
choose a domain from the repository's `domains/` (or upload a zip), see what will be modelled and what stays raw,
confirm. Re-import of an existing domain asks to replace the draft.

## 2. FAQ

Table (id, question, answer start, pattern summary, validation badge) with search. A form opens at the side:
`question`, `answer` (verbatim reply), `paraphrases` and `asr_variants` as editable string lists (counts shown
against the minimums 3 and 1), and the **pattern**: `all_of` as a list of word groups (each group a chip list),
`any_of`, `none_of` as chip lists, `priority`, and `regex` (collapsed, marked "only when word groups cannot say it"). A
reading of the pattern in plain words is shown below ("needs one of [card, debit] and one of [lost, stolen]; not
[statement]"). Reorder by drag. Items are saved per entry; the badge shows the loader's message for the entry.

## 3. Tools

List with badges for `risky`, `requires: verified`, `verifies`, `retry`. The form edits `params` (ordered list of
names), flags, and the fake API: `rules` (ordered list; each has a `when` map of parameter to value, and either
`return` as key-value rows or `error` as a code, plus `delay_ms`) and `default`. Deleting a tool shows the flows that
call it. The form states the loader's cross-checks as they apply (a risky tool cannot have `retry`; protected tools
need exactly one verifying tool).

## 4. Flow list

Flow id, trigger summary, buttons, node count, `role: verification` marker, validation badge. A flow belongs to the current bot (one language). An optional sibling marker shows whether the same flow id exists in the other bots of the domain and, if the sibling check is on, whether the structure matches. **New flow** (blank or copy, also from a sibling bot).

## 5 and 6. Flow viewer and editor

Layout: canvas in the middle, node palette on the left (editor only), properties panel on the right, validation
strip at the bottom. ST1 ships the viewer: canvas, pan and zoom, minimap, select a node to see its properties
read-only. ST2 turns editing on. There is no YAML view.

### Node kinds, handles and transitions

The set of node kinds and the exits of each come from the engine (`NODE_TYPES` and the `edges` function of each type
in `voxstage/rules/flows.py`). The editor draws one exit handle per name below. A flow also has `start`, drawn as a
**Start** marker with one outgoing line.

| Kind | Waits for caller | Exits (handle label: YAML key) | Notes |
|---|---|---|---|
| `say` | no | `next` | text with `{}` fields |
| `ask` | yes | `next` | slot, prompt, extractor, `length`, `choices`, `interruptible` |
| `form` | yes | `next` | ordered `slots` (each an ask spec without `next`), `say_when_ready` |
| `confirm` | yes | `yes`: `on_yes`, `no`: `on_no` | both required |
| `call` | no | `ok`: `on_ok` (required), `error`: `on_error` (optional) | tool, args; `error` handle may stay unconnected |
| `branch` | no | one exit per case (`cases[i].next`, labelled with its `when`), `else` (required) | cases are ordered, first true wins; reorder by drag |
| `notices` | no | `next` | optional `ids` |
| `goto` | no | `next` | |
| `end` | - | none | `action`: none, `handoff` (with `reason`), `end_call` |

Rules the canvas enforces while drawing, before the loader is asked: every exit handle holds at most one line (a
node names exactly one successor per exit); required exits must be connected before a save is "complete" (an
unconnected required exit is marked on the node; saving is still allowed); a line cannot end at the Start marker; a
flow needs one `start` and at least one `end`.

Visual language: one colour and icon per kind; waiting kinds (`ask`, `form`, `confirm`) have a double border (they
are where a loop is allowed); `call` nodes show the tool name and a `risky` badge; `branch` lists its cases on the
node; the `end` node shows its action. Lines are labelled with the handle (`next` unlabelled, `yes`/`no`,
`ok`/`error`, the case condition, `else`). Back-edges (a retry loop to an earlier `ask`) are drawn curved.

### Properties panel

Shows the form for the selected node, keyed by kind, with the loader's allowed keys exactly (unknown keys cannot be
produced). `slot`/`extractor`/`length`/`choices` with their load-time rules (`choices` only with `choice`, `length`
only with `digits`), `tool` picker (fills `args` with the tool's `params`; an `args` key set must equal them),
template fields with `{}` highlighting and a dropdown of names in scope (slots of this flow, `customer`, `policy`,
`result`) and the formatters (`money`, `count`, `date`, `default`), and `branch` conditions with the same names.
Flow-level properties (when nothing is selected): `id`, `triggers`, `buttons`, `captures`, `interrupts`, `carry`,
`prefill`, `verification`, `role`. The panel shows the sensitive-slot constraint when a slot is in
`sensitive_slots`.

### Editing operations

Add node from the palette (drag or click; a new node is placed next to the selection), connect handles, delete
node or line (with its lines), duplicate node, change kind (keeps compatible keys), rename node id (updates every
line that pointed to it), undo/redo (client-side history of the working copy), copy a flow's structure from a sibling bot
(ST2: node ids, kinds and links are copied, texts and triggers are left to be written in this bot's language). The working copy lives in the browser; **Save** sends the whole flow, and saving is
also triggered on idle. A `409` offers reload or overwrite.

### Validation display

- The strip lists the items of the last validation (from `PUT` quick checks immediately, from the loader on
  **Validate** and on idle after save). Click an item: the canvas pans to the node and selects it.
- A node with an error gets a red border and a badge with the count; a warning gets amber. The hover text is the
  engine's message unchanged. Items without a node are shown on the Start marker or on the flow header.
- Flow-level messages (unreachable nodes, a loop without waiting, no `end`) mark the nodes the message names.
- The loader stops at the first problem in a file, so one item per file is normal; the strip says "the engine reports
  one problem per file at a time" so a clean list is not mistaken for a clean flow.
- Studio-only items: the optional **sibling check** (off by default; when on, it warns where a sibling bot's flow of
  the same id differs in node ids, kinds, `next` links, tools or arguments; the engine's twin test is a dataset rule,
  not a loader rule, and never blocks a publish) and an unused-slot hint.

### Automatic layout

Dagre, left to right (top to bottom as an option), applied (a) on first load when nodes have no stored position, (b) on
demand with **Auto layout**, and (c) to a newly added node group only (placed near the node it was created from).
Ranks follow the graph from Start; back-edges are ignored for ranking. After auto layout the positions are saved like
any move. Dragging, zoom and viewport are saved to the layout table (debounced) and do not mark the flow as changed.
Dagre is chosen because React Flow's documentation recommends it for tree-like flows; ELK is the fallback if edge
crossings in the big flows (`time_deposit_signup`, `return_request`) prove poor (to be measured in ST1).

## 7. Validation panel (domain level)

All items of the domain, grouped by file (FAQ, tools, each flow, notices), filter by severity and language; each links
to the screen and object. **Validate** runs `POST validate`; the result is tied to the draft revision and goes stale
when anything changes.

## 8. Publish, history, diff, rollback

- **Publish** (top bar): enabled when the last validation is for the current revision and has no errors. The dialog
  shows what changed since the last publication (file list and counts), asks for a note, and publishes. On `422` it
  shows the report.
- **History**: publications newest first with number, note, kind (publish / rollback), author, time. Selecting one
  shows its files and a diff against the previous publication, against another publication or against the draft
  (file by file, unified text diff of the exported YAML; the flow diff also lists added, removed and rewired nodes).
- **Rollback** on a publication: explains that this creates a new publication and replaces the draft; blocked with
  a prompt when the draft has unpublished changes (discard or cancel). Download as zip.

## 9. Notices and wording (ST3)

Notices: ordered by priority, drag to reorder (priorities renumbered but unique), text (literal, no `{}`), `applies_when`
expression over the flow's slots. Wording: the fixed set of situation keys, all required, with the key's meaning
and, for the keys that need `{value}`, a check for it.

## 10. Settings (ST3)

Forms for `config` (fallback misses and action, ask re-prompts, max parked, correction limits, verification
attempts, tool timeout and failures), `confirm` yes/no words, `commands` patterns, `corrections` and `confusions`,
sensitive slots and read-back slots. Policy values follow the format the engine track merges in R14 and appear here only
after that; until then they are raw files.

## 11. Preview (ST3)

A chat window next to the flow editor or on its own page: choose language and source (draft or a publication), edit
the scenario setup (`customer`, `policy`, `now`), type or press a button or enter keypad digits. Each reply shows the
bot text, actions (hand-off, end call) and the trace; the current node is highlighted on the flow graph.

## Accessibility and look

Keyboard: arrow keys move the selection, `Delete` removes, `Ctrl+Z/Y` undo/redo, `/` opens the palette. Light and
dark theme. Korean and English UI strings are not translated in v1 (UI in English, as the documentation).
