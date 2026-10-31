# Spec ST2: publication history, diff, rollback, sibling check, roles

Status: **draft, details open** (owner: ST2 before ST3, 2026-10-31). Nothing here is built until the spec is approved.
Read first: this file, [docs/studio/README.md](../../studio/README.md) (decisions 1 to 6 of 2026-10-27, esp. 3 and 4),
[api.md](../../studio/api.md) "Validation, publication, history", [data-model.md](../../studio/data-model.md)
"Publications", [screens.md](../../studio/screens.md) section 8, ADR 0012 and 0013. Do not edit `voxstage/`. Work on
branch `wip/studio-st2`, finish on `dev`.

## What is already there (ST1 and the UI pass), so it is not in this spec

Flow editing for the nine node kinds with the properties panel, layout storage, validation display on the cards and in
the panel, validation and publishing from the editor and the top bar, the publication list with its files and zip
download (`GET /bots/{b}/publications`, `.../{n}`, `.../files/{path}`, `.../export.zip`), the tables `user`, `role`,
`user_role` (baseline migration) with the seeded local user and the `require_role` dependency that allows everything,
and `updated_by` and `published_by` columns that are already filled with the local user's id.

## What this spec adds

| # | Piece | Today |
|---|---|---|
| 1 | **Diff** of a publication against the one before it, another publication or the draft | History shows files only; no diff endpoint |
| 2 | **Rollback** to a publication | No endpoint, no screen |
| 3 | **Sibling check**: compare a bot's flows with the same-id flows of the other-language bots of its domain | `bot.copied_from` exists, no check |
| 4 | **Publish dialog summary**: what changed since the last publication (screens.md 8) | The dialog asks for a note only |
| 5 | **Roles**: who may edit, publish, roll back, delete; author names in the history | One local user, everything allowed, ids stored but not shown |
| 6 | **End-to-end test** (Playwright, decision 6 of 2026-10-27): import, edit, validate, publish, roll back | None |

## Decisions to settle before approval

Asked one at a time, recommendation first. A row is edited to DECIDED when the owner answers.

| # | Question | Recommendation and why | Status |
|---|---|---|---|
| D1 | A bot's publication also holds the **domain's shared files** (`tools.yaml`, `types.yaml`, slot lists, raw domain files). Does a rollback restore them too? | **No: restore only the bot's own files.** The shared files belong to every language of the domain; rolling back `bank-en` must not silently change `bank-ko`'s API connections or types. The new publication is N's own files plus the domain's current shared files, and it must pass the engine's validation or nothing changes (`422` with the report). A later option "also restore the shared files" can be added with the list of affected bots, if wanted | OPEN, asked first |
| D2 | **Diff unit**: raw text only, or a summary by meaning? | **Both, summary first.** A summary by what an operator edits (questions added, changed, removed; scenarios with steps added, removed, rewired, text changed; API connections; each settings file) with the unified text diff of the exported YAML under "자세히". Text alone says "line 212 changed", which no operator can use; the summary alone hides what exactly changed | OPEN |
| D3 | **Sibling check**: when does it run, what does it compare, does it ever block? | **On demand and in the publish dialog, as warnings, never blocking.** Compare only structure of same-id scenarios (step ids, kinds, links, API and its 속성 connections); never texts, which differ by language. Say which scenarios exist in one language only. The engine's twin test stays on `domains/`; a studio bot may differ on purpose (README: "optional report, not a rule") | OPEN |
| D4 | **Roles**: enforce them, and how is the user chosen without a login? | **Enforce in the API, choose the user with a header, no screen.** `editor` edits content, `publisher` also publishes and rolls back, `admin` also imports and deletes bots; the user is the `X-Studio-User` email, defaulting to the local user (who has all roles), so the app behaves as today and tests can act as an editor. The history shows the author's display name. A login screen and a user admin screen stay out (api.md "Not in v1") | OPEN |
| D5 | **Retention**: keep every publication? | **Yes, forever.** They are small text and the history is the audit trail; nothing deletes a publication, and deleting a bot deletes its history (as it does today) | proposed, no question needed unless the owner objects |

## Build order

1. **Diff (backend).** `studio_backend/diffs.py`: file status (added, removed, changed) and unified diffs between two sets of
   files, where a set is a publication's `publication_file` rows or the draft export (`export_bot`); the summary by meaning
   from the parsed YAML (D2): FAQ entries by id (and their pattern), scenarios by id with steps added, removed, changed,
   rewired, API connections by name, settings files by kind. `GET /bots/{b}/publications/{n}/diff?against={m | draft}`
   returns `{files: [{path, status, unified}], summary: {...}}`. The default `against` is the publication before `n`.
2. **Rollback (backend).** `POST /bots/{b}/publications/{n}/rollback` `{note, discard_draft}` per D1: refuse (`409`) when the
   draft has unpublished changes and `discard_draft` is false (decision 3); build the new files from N's own files plus the
   current shared files; validate them with the engine loader (`422` with the report, nothing changed, when they fail); in one
   transaction store a publication of kind `rollback` with `restored_from_number`, replace the bot's draft meaning rows from the
   files (`portable.load_files`, the importer's reading of text instead of a directory), bump `draft_revision`, and write the export
   directory. Layout (decision 4): positions of nodes that still exist stay, nodes that no longer exist lose theirs, nodes
   without one are placed by Auto layout. `studio_settings` (hand-off number, 정책값) and `origin` are not in a publication, so
   they stay as they are.
3. **Sibling check (backend).** `GET /bots/{b}/siblings/check` returns warnings per scenario (`only_here`, `only_in`,
   `structure_differs` with the first difference: a step, a link, a tool or a binding), per D3. Nothing in validation or
   publication depends on it.
4. **History screen.** Select a publication: its summary against the previous one (D2), a "비교 대상" choice (이전 버전, 다른
   버전, 지금 초안), the file list with the unified diff under "자세히", **이 버전으로 되돌리기** (rollback dialog: says it
   creates a new version and replaces the draft, asks to discard unpublished changes when there are any, takes a note), the
   rollback kind and `restored_from_number` shown on the list ("3번째 버전으로 되돌림").
5. **Publish dialog summary.** The summary of the draft against the newest publication above the note field, plus the sibling
   warnings (D3); `409 nothing to publish` is told before the user types a note.
6. **Roles.** `require_role` reads `X-Studio-User` (D4) and checks the role of each write endpoint; `403` with the missing
   role; the history joins `published_by` to the display name. Migration only if the seed needs new rows.
7. **End to end.** One Playwright test: import `bank`, edit an FAQ answer, validate, publish, edit again, publish, read the
   diff, roll back to 1, and check the draft and the export directory equal publication 1's own files.

After each numbered item: backend tests, `npm run build`, `npm test`, `tsc --noEmit`, the engine's
`python -m unittest discover -s tests` stays green, commit to `wip/studio-st2`, push; the studio commit rules of `AGENT.md`
apply (author, no co-author trailer, no secrets).

## Tests

- Backend (real Postgres): diff of two publications, of a publication against the draft, and `against` defaults; the summary
  names the changed FAQ entry, a scenario with an added and a rewired step, a changed API connection, a changed settings
  file; rollback creates publication `n+1` with kind `rollback`, the draft's export equals N's own files, other bots of the
  domain and the shared files are unchanged (D1), `409` with an unpublished draft and `discard_draft: false`, `422` leaves
  everything as it was when N no longer validates against the shared files; layout rules of decision 4; sibling check for
  identical, one-sided and rewired scenarios; role checks (editor refused on publish and rollback, publisher refused on delete).
- Frontend (Vitest): History compare view and rollback dialog (states: unpublished changes, confirm, failure), the publish dialog
  summary and the warnings, the 403 message.
- End to end: item 7.

## Done when

- A publication can be compared with the previous one, another one and the draft, with a summary by meaning and the text diff.
- A rollback gives a new publication of kind `rollback`, a draft equal to it, history intact, and no change to other languages'
  bots or the domain's shared files (D1).
- The sibling check lists differences between `bank-en` and `bank-ko` (none for the imported pair) and a deliberately broken
  copy shows them; publishing is never blocked by it.
- An `editor` cannot publish, roll back or delete; the local user can do all.
- Backend, frontend, end-to-end tests, typecheck and build pass; `voxstage/` has zero diff against `dev`.

## Not in ST2

Notices and wording forms, settings forms, 정책값 in the engine's format (ST3); a chat window (built as 대화로 테스트); restoring
single files or single entries from a version; a login screen, user management, comments, locking (api.md "Not in v1");
publishing several bots at once; deleting or pruning publications.
