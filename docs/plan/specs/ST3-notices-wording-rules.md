# Spec ST3: notices, wording, rule words, slot lists, policy values

Status: **draft, details open** (written 2026-11-01). Nothing here is built until the owner approves it.
Read first: this file, [docs/studio/README.md](../../studio/README.md), [screens.md](../../studio/screens.md) sections 9 and 10,
[data-model.md](../../studio/data-model.md), [R5](R5-notices-registry.md) (registry decisions R5-1, R5-2), R7b, R8, R9, R14.
Do not edit `voxstage/`. Work on branch `wip/studio-st3`, finish on `dev`.

## What is already there, so it is not in this spec

- **대화로 테스트** (the preview chat, screens.md section 11) is built, with the setup (`customer`, `policy`, `now`) and the
  trace. ST3 only reuses it to try wording.
- **기본 설정** on 개요: the engine's `rules/config.yaml` limits (fallback, ask, switch, correction, verification, tools),
  the hand-off number and the policy values (`studio_only`), with the list of flows that use each policy key.
- Language starters hold the 17 wording keys and the four rule files for a new bot (ST-NEWBOT), and a copied bot counts
  `to_translate.notices`.

## What this spec adds

| # | Piece | Today |
|---|---|---|
| 1 | **Wording** (`wording:` in `notices.yaml`): the 17 situation keys, text only, with the key's meaning and the `{value}` check | `notices.yaml` travels as a raw file; no form |
| 2 | **Fixed notices** (`notices:`): text, order, `applies_when` | the same raw file |
| 3 | **Rule words**: `confirm.yaml` (yes and no words), `commands.yaml` (cancel, back, agent patterns), `corrections.yaml`, `confusions.yaml` | stored as settings rows, no form |
| 4 | **Slot lists** of the domain: `sensitive_slots` (keypad only) and `readback_slots` (read back after filling, with its format) | stored as shared settings, no form |
| 5 | **Policy values**: warn when a flow uses a key that has no value | values can be typed, nothing checks them |
| 6 | **Translation tracking** for wording and notices of a copied bot | counted, cannot be cleared |

## Decisions to settle before approval

Asked one at a time, recommendation first. A row is edited to DECIDED when the owner answers.

| # | Question | Recommendation and why | Status |
|---|---|---|---|
| D1 | **Where do these forms live?** | **Two new menu pages.** "안내 문구" (fixed notices and the 17 wordings, one language) and "응답 규칙" (yes and no words, commands, corrections, confusions). The slot lists go on the existing 데이터 page, because they belong to the domain and are shared by every language. Wording and rule words are per bot, the slot lists are per domain, so mixing them on one page would hide that a slot-list change reaches the other language | OPEN, asked first |
| D2 | **How much of the wording can be edited?** | **Text only.** The 17 keys are the engine's fixed set and all are required, so the form shows each key with when it is said (plain Korean), its text, a check that `{value}` is present where the engine needs it (`readback`, `correction.offer`) and absent where it does not, and a "기본 문구로 되돌리기" that copies the language starter. No adding or removing keys | OPEN |
| D3 | **How is `applies_when` of a fixed notice entered?** | **A text box with a live check, plus a list of the attributes to click in.** The expression language is the engine's; the studio compiles the text with the engine and shows the error under the box, so it can never save something the engine will refuse. A point-and-click builder is a later step | OPEN |
| D4 | **Can an operator try the rule words?** | **Yes, a small test box on 응답 규칙.** Type a sentence and see which command, yes or no, or correction it triggers, computed by the engine's matcher. Without it, editing `any_of` lists is guesswork. The 대화로 테스트 stays for whole conversations | OPEN |
| D5 | **Policy values: stay studio-only?** | **Yes.** The engine reads `{policy.<key>}` from the request's `setup.policy` (R14), not from a file, so a published pack has no value in it. Keep the values in `studio_settings`, never export them, and add a validation warning when a flow uses a key with no value | OPEN |
| D6 | **Translation tracking for wording and notices** | **Per item.** Saving a wording key or a fixed notice of a copied bot marks that item translated; the overview counter goes down as the list is done. Same rule as FAQ entries and flows | proposed, no question needed unless the owner objects |

## Build order

1. **Model `notices.yaml` (backend).** New bot setting kind `notices` (`BOT_SETTINGS` gets `"notices": "notices.yaml"`), a
   migration that moves each bot's raw `notices.yaml` row into it (the way the type dictionary moved, migration 0003), the
   exporter and the bot creation code follow. Export stays byte-compatible after a parse (ADR 0013).
2. **Wording and fixed notices API.** `GET/PUT /bots/{b}/notices` with a revision; checks as the engine's loader does (all 17
   keys, `{value}` rules, unique priorities, text without `{}` for fixed notices); `POST /bots/{b}/notices/check-expression`
   (D3) compiles an `applies_when` text with the engine and returns the error or the attributes it names.
3. **안내 문구 page.** Two tabs: 고정 안내 (list, drag to reorder, priorities renumbered 10, 20, 30, text, `applies_when`
   with the check, "항상 말하기" when empty) and 상황별 문구 (the 17 keys, meaning, text, `{value}` check, reset to
   the starter). Dirty and save follow the other forms.
4. **Rule words API and page (D4).** `GET/PUT /bots/{b}/rules/{confirm|commands|corrections|confusions}` with the loader's
   checks, `POST /bots/{b}/rules/test` (a sentence in, the matches out, using the engine's tokenizer and matchers). The
   page reuses the word and pattern inputs of the flow trigger editor; confusions as pairs of numbers.
5. **Slot lists on 데이터.** `sensitive_slots` as a list of attributes (only attributes that are `digits` fit the engine's
   keypad check, so only those are offered), `readback_slots` as attribute plus format from the engine's list; saves bump the
   domain's shared revision like the types do.
6. **Policy warning and translation tracking (D5, D6).** Validation warning `policy_value_missing`; saving wording or a
   notice calls `mark_translated`.
7. **End to end.** Extend the Playwright test: edit a wording, add a fixed notice, publish, and check the export directory
   and a chat reply that says the new wording.

After each item: backend tests, `tsc --noEmit`, `npm test`, `npm run build`, the engine's tests stay green, commit to
`wip/studio-st3`, push; the studio commit rules of `AGENT.md` apply.

## Tests

- Backend (real Postgres): the migration moves a raw `notices.yaml` into the setting and the export equals the source; wording
  checks (missing key, `{value}` where not allowed, duplicate priority, `{}` in a fixed notice); `applies_when` check with a
  good, a bad and an attribute-naming expression; rule file checks and the sentence test for each file; slot lists refuse a
  non-`digits` sensitive attribute; the policy warning; marking translated; roles (editor may edit, as everywhere).
- Frontend (Vitest): the two pages' dirty, save and error states, reorder renumbering, the `{value}` message, reset to
  starter, the test box.
- End to end: item 7.

## Done when

- Every wording key and fixed notice of a bot can be edited in the studio, saved, published, and the engine speaks it.
- The four rule files and the two slot lists have forms with the engine's own checks; nothing the engine refuses can be saved.
- A copied bot's translation counter reaches zero after its wording and notices are saved.
- Backend, frontend, end-to-end tests, typecheck and build pass; `voxstage/` has zero diff against `dev`.

## Not in ST3

Adding or removing wording keys, a point-and-click `applies_when` builder, a user-facing policy file or an engine change to read
policy from files, text-to-speech tuning, automatic translation, bulk edit across languages, comments and approval flows.
