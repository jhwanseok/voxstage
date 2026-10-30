# Studio UI: design notes for the mockups

Mockups: `/mock/home`, `/mock/faq`, `/mock/flow` (static data; not wired to the API). Real screens follow after approval.

## Reference and what is taken from it

Reference named by the owner (2026-10-28): the ALF console of Channel Talk. Only layout, information placement and tone are
used; no logos, brand assets or product copy, and **no functions** (no metrics dashboard, knowledge upload, code
nodes, rule engine). Scope stays ST1 to ST3. Sources read:
[channel.io/kr/talk](https://channel.io/kr/talk), [channel.io/kr/alf-customer](https://channel.io/kr/alf-customer),
[help center: rules](https://docs.channel.io/help/ko/articles/%EA%B7%9C%EC%B9%99-b43e19a1),
[help center: tasks](https://docs.channel.io/help/ko/articles/%ED%83%9C%EC%8A%A4%ED%81%AC-ALF-v2-2a16be8b).
Secondary: Voiceflow, Botpress Studio, Dialogflow CX (flow canvases).

| Pattern seen | Used here | Not adopted (outside the approved design) |
|---|---|---|
| Card list with a condition tag per card | Home bot cards with status chip and counts | Per-card on/off toggle (the engine has no such switch) |
| Knowledge: left grouping + table with state tags | FAQ: left "보기 기준" rail (all / published / edited / needs attention) + wide table with state tags | Folders, resolution rate, reference counts, uploads |
| Task builder: trigger area, then step cards joined by "next step" | Scenario: trigger card first ("이런 말을 들으면 시작해요", 포함/제외 chips), then big step cards | Code and instruction steps |
| Polite, short Korean copy, verb-led buttons | All UI strings | Emoji, marketing tone |
| White ground, generous space, rounded cards, one accent | Tokens in `mock.css` | |

## Audit against the ten principles (condensed, self-scored; evidence is in the mock source)

Total 24 / 30 after this pass, so refine, not redesign.

| # | Principle | Score | Evidence and what was changed |
|---|---|---|---|
| 1 | innovative | 2 | Familiar console pattern with one improvement: the flow reads top to bottom like a call script, whole flow visible on open. |
| 2 | useful | 3 | Each screen has one primary task: pick a bot, edit a question, read a flow. Actions sit in the top bar. |
| 3 | aesthetic | 2 | One system (Tailwind tokens, 8 pt spacing, radius 8/12). Flow node colours are the busiest part; limited to a 4 px bar and a chip. |
| 4 | understandable | 3 | No internal terms (`confirm`, `triggers`, `all_of` become "예/아니오 확인", "시작하는 말", "반드시 포함"). Status chips say what to do. |
| 5 | unobtrusive | 2 | Chrome is quiet; the status chips in the top bar are always on, acceptable because they are the state the user acts on. |
| 6 | honest | 3 | Every label maps to real behaviour: "게시 안 된 변경" = `has_unpublished_changes`; risky call badge = engine `risky`. No on/off toggle was drawn because the engine has none. |
| 7 | long-lasting | 2 | Plain cards and system type; no gradients or trend type. |
| 8 | thorough | 1 | Focus rings and keyboard rows added; **empty, loading and error states are not yet drawn** (to do in the real screens). |
| 9 | environmentally friendly | 2 | Tailwind adds CSS only; mock chunk lazy-loaded; no idle animation; reduced-motion respected. Dark mode not done yet. |
| 10 | as little design as possible | 3 | Home has three tiles and cards; FAQ has one list and one drawer. |

Fixes made in this pass: text contrast (slate-400 text replaced by slate-500, brand blue darkened to `#4f4fe0` so white-on-brand is
5.95:1), keyboard focus ring, tabular numbers, keyboard-operable table rows, labelled icon buttons, trigger moved into the flow as its
first card, FAQ filter rail, friendlier copy.

Contrast checked (WCAG AA, normal text): white on brand 5.95, slate-500 on white 4.76, brand-700 on brand-50 7.71, emerald-700 on
emerald-50 5.21, amber-700 on amber-50 4.84, rose-700 on rose-50 5.72.

## Checklist for the real screens (must hold before a screen is "done")

- Information hierarchy: one page title, one primary action, state chips in plain Korean.
- Spacing on an 8 pt grid (4 for tight gaps); type scale 12 / 14 / 16 / 20 / 24.
- Colour: AA contrast for text and 3:1 for icons and borders that carry meaning; status never by colour alone (icon or text too).
- States: empty (what to do next), loading (skeleton), error (what happened, how to retry), success (saved feedback) for every list and form.
- Keyboard: every row, button and node reachable; visible focus; Esc closes the drawer; Enter opens a row.
- Korean copy: short polite sentences, "~해 보세요" for guidance, no internal terms (flow, trigger, slot, node id appear only in a secondary "개발 정보" line).
- Charts and numbers (home summary): big number plus label plus one-line meaning; no dual axes; counts use tabular numbers.
- i18n: all strings in one dictionary, Korean default, English switch.

## Real screens (2026-10-28): owner feedback and what changed

Tokens and components: `src/ui/DESIGN-SYSTEM.md`. The mockups stay under `/mock/*` as the reference.

### (1) Bot defaults on 개요

Engine values (`rules/config.yaml`: re-prompts, misses, corrections, verification attempts, tool failures and timeout,
parked flows, and the action when each limit is passed) are edited here and published like any other draft change.
The hand-off number and the R14 policy values are not read by the engine; owner decision 2026-10-28 (Q44): keep both
in the studio only (`bot.studio_settings`), marked 엔진 미반영, never in the published files, and no engine item until
they are needed.

### (2) FAQ edit form was "정신없다": before and after

| Before (mock `/mock/faq`) | Why it was noisy | After (`/b/<bot>/faq`) |
|---|---|---|
| Three columns at once: filter rail, table, 460 px drawer | Three panels compete; the table squeezes to half width while editing | Full-width list; the editor is a 560 px sheet over a dimmed list, so only one task is on screen |
| The same filter twice (rail and a select) | Two controls for one choice | One segmented control: 전체 / 게시 후 고친 질문 / 확인이 필요한 질문, with counts |
| Four columns: question, answer, keywords, state | Answer text and keywords pull the eye from the question | Question in bold with a one-line answer under it; keywords in a narrower column, hidden on small screens |
| Drawer shows everything open: question, answer, three chip inputs, an example box, paraphrases, ASR | Four jobs (wording, matching, examples, ASR) at equal weight; long scroll before the save button | Order by how often a field is edited: wording first (always open); then 알아듣는 조건, 같은 뜻의 다른 말, 잘못 알아들은 예시 as sections that show a one-line summary when closed and open themselves only when something is missing |
| Matching rule as raw chips with hints such as "각 줄에서 하나 이상" | The rule is hard to read back | Each 반드시 포함 row says "이 중 한 단어 이상"; the whole rule is read back as one Korean sentence under the inputs and as the closed summary |
| Priority and regex mixed with the main rule | Rarely used, but always visible | Under 고급 inside the rule section |
| Id in monospace under the title | Internal name in the most visible place | Under 개발 정보 (closed); editable only for a new question |
| Errors not drawn; save always active | No feedback | Save is disabled until something changed; missing wording blocks the save with one notice; counts below the guidance (3 paraphrases, 1 ASR) are saved and flagged in the list as 확인 필요 |
| Footer: 삭제 · 취소 · 저장 | Delete next to Cancel | Delete on the far left in red, then the unsaved state, 취소, 저장 |

### (3) Scenario editing

The canvas keeps the approved layout (trigger card first, cards top to bottom, exits under each card). Now: 단계 추가 menu
(nine kinds, joined after the selected step when it has a free exit), drag from an exit dot to a card to connect, drag
an edge end to reconnect, select an edge or a card and press Delete, a property form per kind with "이어지는 곳" selects
as the keyboard alternative to dragging, rename with all links updated, 시나리오 설정 for the trigger words and buttons.
초안 저장 (also Ctrl+S) sends the meaning to `PUT /bots/<b>/flows/<id>` and the positions to `/layout`; the toolbar
then offers 검증하기, and after a pass 게시하기 (the same dialog as the top bar). Engine problems are drawn on the
cards (red ring, count) and listed in the panel; local checks (no start, a link to nowhere, unreachable step, no end)
show before saving.

### (4) URL bug

Cause: `<Navigate to="home" />` and `<Navigate to="faq" />` inside `path="*"` routes. React Router v7 resolves a relative
`to` against the whole URL inside a splat route, so a menu item without its own route ("API 연결" in the mock) redirected
to `/mock/api/home`, which matched `*` again, and so on (`/mock/api/home/home/home/...`). The real app had the same
pattern (`/b/<bot>/<unknown>/faq/faq/...`). Fix: every link and redirect is built by `src/paths.ts` and is absolute.
Regression tests: `src/routes.test.tsx` (redirect targets, and repeated clicks on the menus including "API 연결").

### Review pass on the running screens (5710, real data)

| Skill | Finding | Fix |
|---|---|---|
| design-critique | Header said "은행 상담봇" while the name field showed the raw import title "bank (ko)" | The form shows the readable name; a save stores it |
| design-critique | Cards showed whole expressions such as `{'저축' if to_account == 'savings' else '입출금'}` | Simple names stay (`amount`), longer expressions read "값" with the full one in the tooltip |
| design-critique | Adding a step blanked the page (a placeholder card with no data reached React Flow) | New positions are kept in a ref until the card is built; the card guards an empty body |
| design-critique | Overview carried a filler line of icons under the tiles | Removed |
| accessibility-review | Clickable table rows were `tr tabIndex` (announced as a row, not an action) | A real button in the first cell; the row stays clickable for the mouse |
| accessibility-review | Segmented filter claimed `radio` roles without arrow keys | Toggle buttons with `aria-pressed` |
| accessibility-review | Canvas steps reachable only by mouse | A step list in the panel, and 이어지는 곳 selects for every exit |
| accessibility-review | Word-tag remove button 20 px; editor had no `main` landmark | 24 px target; `main` added; tab and tabpanel wired with ids |
| ux-copy | 을/를 after a vowel ("시나리오을 불러오지 못했어요") | `eul()` picks the particle (tested) |
| ux-copy | Tile "연결된 API" against menu "API 연결"; vague "다른 곳에 문제가 있어요" | One term "API 연결"; "다른 파일에 고칠 곳이 있어요" |

Open (not done here): strings are not yet in one i18n dictionary (checklist item); window.confirm dialogs keep the
browser's OK / 취소 labels; the main chunk is over 500 kB (React Flow and dagre, a lazy split is possible).

## ST4 (2026-10-29): data types, roles and binding (ADR 0014)

Built to the accepted ADR, then aligned to the engine's R16a commit (records only, one session role `caller`,
`default: {from}`, the field gives an `ask` its extractor).

| Screen | What the user sees | Why this shape |
|---|---|---|
| 데이터 (new menu, after 시나리오) | 값의 종류 (types, each with its fields and "where it is used") and 통화 전체에서 쓰는 값 (the 발신자, filled by the identity check) | Shared by every language of the domain, like API 연결, and said so on the page; the type name and field names live under 개발 정보 or in a small 이름 box, the label is what is shown |
| Type sheet | 표시 이름, one card per field: 표시 이름, 형식, 이름, 자릿수 only for digits, 보기 only for choice | No nesting (Q55): the field type list holds only the engine's extractors. A type in use cannot be deleted; removing a field a scenario uses asks first and names the scenario |
| 시나리오 설정, 이 시나리오의 사람과 값 | One card per role: 표시 이름, 값의 종류, "다른 사람과 같을 수 있어요" with 누구와 같은지 (another role of the scenario, same type) | The question is the explicit `confirm` step's own sentence (P3); when the step is missing the card says so and 확인 단계 추가 adds it |
| 묻기 step | 받는 값: "예약자의 이름" instead of a free slot name when the flow has roles | The format comes from the type, so the extractor select is hidden |
| API 호출 step | One card per parameter: 어디서 가져올까요 (사람과 값 / 앞 API 결과 / 직접 넣기 / 예전 방식), then the matching second input | Values whose type does not fit are not offered; an earlier result that exists only on some paths is listed disabled with the reason; a stored binding that no longer fits shows as an error in its row |

Labels (Q54) are written into the files per language; the other language's label is kept when one is edited.

Review pass: design-critique found the field card too tall (length shown for every text field) and moved 자릿수 next to
이름; ux-copy fixed particles after labels with a `josa()` helper ("방문자가 예약자와 같은지 물어요"); accessibility-review
found that every sheet re-ran its focus trap on each render and threw the focus back to the first field while typing
(also on the FAQ and API sheets). Fixed in `useFocusTrap`, regression test `src/ui/sheet.test.tsx`; a new field takes
the focus.

### Terms (owner feedback, 2026-10-29)

The owner calls what a scenario collects or an API returns a **속성**, not a 값. Rule now: the collected or stored
thing is a 속성, a slot of a type is a 항목, a binding picks the 가져올 속성 or a 고정값; only a value the user types
(a constant, a stored choice, the values the identity check reads) keeps 값.

| Before | After |
|---|---|
| 값의 종류 (heading, button, sheet title, select label) | 속성 종류 |
| 필드, 필드 추가, 필드 n개 | 항목, 항목 추가, 항목 n개 |
| 통화 전체에서 쓰는 값 / 통화 전체 값 | 통화 전체에서 쓰는 속성 / 통화 전체 속성 |
| 상담봇이 고객에게서 받는 값의 모양이에요 | 상담봇이 고객에게서 수집하는 속성의 모양이에요 |
| 이 시나리오의 사람과 값 / 사람이나 값 추가 | 이 시나리오의 속성 / 속성 추가 |
| 받는 값 (묻기 단계) | 받을 속성 |
| 넘길 값 / 연결 안 된 값 n개 / 이 API는 받는 값이 없어요 | 넘길 속성 / 연결 안 된 속성 n개 / 이 API는 받는 속성이 없어요 |
| 어디서 가져올까요 | 가져올 속성 |
| 사람과 값 / 앞 API 결과 (source groups) | 시나리오에서 수집한 속성 / API로 얻은 속성 |
| 직접 넣기 | 고정값 (its input stays 넣을 값) |
| 받은 값의 이름으로 (예전 방식) / 받은 값의 이름 | 이름으로 받은 속성 (예전 방식) / 받은 속성의 이름 |
| 결과 중 어떤 값 | 결과 중 어떤 항목 |
| 이 변경으로 시나리오에서 쓰던 값이 사라져요 | ... 쓰던 속성이 사라져요 |

The tables above this section keep the words used when they were written.

## 대화로 테스트 (design memo, 2026-10-29)

Owner request: once a bot passes validation, talk to it like a chatbot (text first), with what happened in each turn.

**Engine dependency: none new.** The engine already runs a dialogue on text: `build_manager(domains_dir, domain, lang,
tools)` gives a `FlowManager`; `initial_state(id, setup)` and `respond(state, Utterance(text, source="typed") | Dtmf |
ButtonPress)` return a `DMResult` (reply, new state, actions such as `HandOff`/`EndCall`, and a `trace`). API calls go
through `FakeApiExecutor.from_yaml(tools.yaml)` (the rules and default answers of API 연결), which the studio wraps to
record each call's arguments and result. Collected 속성 are in `state.slots` (`<role>.<field>` for roles), re-asks in
`meta.ask_misses`, the identity check in `meta.verified` / `meta.caller`, call results in `meta.calls`. The studio only
reads these; `voxstage/` is not changed.

**Backend** (`studio_backend/chat.py`, in memory, one process):

| Endpoint | Does |
|---|---|
| `POST /bots/<b>/chat` `{setup: {now?, customer?}}` | Refused (409, with the reason) unless the current draft passed validation. Exports the draft to a temp dir, builds the manager, keeps the session (at most 20, oldest dropped, 30 min idle). The bot's 정책값 (studio-only) go into `setup.policy`. Returns id, the draft revisions it runs, and the flows' buttons |
| `POST /bots/<b>/chat/<id>/turns` `{kind: text \| digits \| button, text}` | One turn: reply, actions, flow and step before and after, 속성 after (changed ones marked), API calls of the turn with the 넘긴 속성 and the result, re-ask count, verified, the raw trace; `stale` when the draft changed since the start |
| `DELETE /bots/<b>/chat/<id>` | Ends the session and removes the temp dir |

**Screen**: a docked panel on the right of every bot screen (not a modal, so the user can keep the scenario open next
to it), opened by **대화로 테스트** in the top bar and on the 검증 page after a pass. Disabled with the reason while the
draft is not validated or has problems. Inside: a header (draft it runs, 처음부터 다시, 닫기), 시작 조건 (기준 시각,
고객 정보) folded, the transcript (고객 on the right, 상담봇 on the left, 상담사 연결 / 통화 종료 as a line), and under
each bot reply a folded **이 턴에서 일어난 일**: 시나리오 · 단계, 수집한 속성 (role.항목 with labels), 호출한 API with
넘긴 속성 and 결과, 재질문 횟수, 본인 확인; the raw trace under 개발 정보. Input: text box (Enter sends), a 말 / 키패드
switch, and the scenario buttons as chips. When the draft changes the panel says so and offers 처음부터 다시.

Built as above (`studio_backend/chat.py`, `src/pages/ChatTest.tsx`). Checked on 5710 with the engine's own case
C14-002 typed into the panel: 영업점 방문 예약 → 휴대폰 끝 네 자리 (키패드 5580) → 본인이신가요 → 네 gives BV1001, and the last
turn shows both role 속성, the `book_visit` call with each 넘긴 속성 and where it came from, and the returned 항목.
Review: on a 1024 px screen the docked panel left no room for the scenario canvas, so below 1280 px it floats over the
page instead (design-critique); the panel is a labelled `aside`, replies are announced through `aria-live`, Enter sends,
the input keeps the focus after each turn (accessibility-review). Not done: a voice mode, a customer-data form in 시작 조건
(only 기준 시각; 정책값 come from 개요), and showing the panel's current step on the canvas.

## ST4 A2 (2026-10-30): typed API params, response items and the call check (ADR 0014 A2, engine R16b)

Engine side, read only (`voxstage/tools.py`, `voxstage/rules/flows.py`, `docs/plan/specs/R16b-api-types-and-flow-check.md`):
`params` is the old list of names or a map `name: {type, length, choices, required}` (a bare type name is allowed);
`returns` maps a response item to its type (`boolean` allowed); a fake API rule's `when` and `return` may name only
declared items, with values of the declared type; the flow check reports `{code, node, parameter, role, field, path}` for
`unbound`, `type_mismatch` and `not_collected` (all problems of one flow at once). What the engine reads and what the
studio keeps: nothing new in the database, the tool body is stored as the file has it.

| Screen | What the user sees | Why this shape |
|---|---|---|
| API 연결, list | 받는 속성 with each one's type ("account_last4 (숫자 자리(키패드 포함) 4자리), note (말 그대로), 선택") and 응답 항목 | A typed tool used to open broken (the form read the map as a list, and a save wrote the list back, so the types were lost); that is fixed first |
| API 연결, form | 받는 속성: one row per attribute with 이름, 형식 (the engine's field types), 자릿수 for digits, 보기 for choice, 꼭 필요해요. 응답 항목: 이름 and 형식 (also 예 또는 아니요) | The type list is the engine's (`PARAM_TYPES`); a row with no 형식 is the old untyped list, written back as the list. Types are all or nothing, because the engine reads the map form only; a 선택 속성 needs a 형식 |
| 가짜 API 응답 규칙 | A condition's name is picked from the declared 받는 속성, a returned item from the declared 응답 항목; the value input follows the type (보기 select, 예/아니요, digits keep leading zeros as text, numbers are numbers) and says "4자리로 넣어 주세요" beside the row | P6: the fake API and the spec cannot drift. The same check runs in the backend on save (`422` with the engine's own sentence) |
| 시나리오, API 호출 step | The 가져올 속성 list offers only attributes whose type fits the parameter by the engine's own rule (`number` takes digits, a boolean fits only text, a choice needs its words inside the parameter's). A response item of an earlier call shows its type and is disabled when it does not fit. A 선택 속성 is not counted as 연결 안 됨 | `fits()` is now a copy of `_fits_type`; only an offer filter, the engine decides at validation |
| 검증 → 편집기 | Each engine item is drawn on its step (red ring and count, already there) and, in the binding form, under its parameter as a sentence: "account: 연결한 속성(acct)을 받지 않고 이 단계에 오는 길이 있어요", and for the path a row of buttons ("그 길: 조건으로 나누기 gate → API 호출 lookup") that select those steps. While the API step is selected the steps and exits of the path are drawn amber | The review memo (5. Publish-check errors on the graph); the check itself stays in the engine, the studio keeps no second copy |

Backend: `validation.py` turns a `FlowCheckError` into one report item per problem (`code`, `node_id`, `parameter`, `role`,
`field`, `path`; `message` is the engine's sentence); `POST/PUT /domains/<d>/tools` run `FakeApiExecutor({tools: {name: body}})`
on the body (without `requires`/`verifies`, which the engine checks across the domain at validation) and answer `422` with
the loader's message, so a tool the engine would refuse for every bot is never saved. Tests: `tests/test_apicheck.py`
(save checks, `unbound`, `not_collected` with the witness path, `type_mismatch` for a constant), `src/lib/tools.test.ts`,
`src/lib/flowcheck.test.ts`, `src/pages/Tools.test.tsx` (a typed tool opens as it is and a save keeps its types and writes
"0042" as text), `src/pages/FlowData.test.tsx`.

Terms (owner rule): 받는 속성 and 응답 항목 for what an API takes and returns; 값 only for what the user types as a
constant (a rule's condition and response values). Not done: the editor does not run the data-flow check live (the engine
does, at 검증하기); the DB's `bank` tools are still the old list form until the domain is imported again, so
their forms show "형식 정하지 않음".

## Skills used

Mockups: `claude-mem:design-is` (audit table above) and the `dataviz` rules for the home summary tiles.
Real screens: `design:design-system` (tokens and component table, `src/ui/DESIGN-SYSTEM.md`), `frontend-design` (direction
review: kept the approved direction, removed template tells such as middle-dot meta strings and monospace ids on cards,
and spent the one bold element on the scenario canvas, where `{slot}` placeholders are tinted inside the spoken
sentence), then `design:design-critique`, `design:accessibility-review` and `design:ux-copy` for the review pass
(findings below). ST4 used `design:design-critique`, `design:accessibility-review` and `design:ux-copy` again on the new screens (above).

## 새 상담봇 만들기 (design memo, 2026-10-29)

Owner request: a bot could only come from the repository's `domains/` folder, so a business or language that is not
there could not be made on screen. The spec had **New bot** (screens.md 1, api.md `POST /bots`, data-model.md "Sibling
bots") but nothing was built.

**Engine facts that shape it** (read only): the FAQ loader takes `lang` from `voxstage/dataset.py` `LANGS` (now `en`,
`ko`), so the language list comes from the engine and nothing else can be offered. `DomainPack.load` needs only
`faq.yaml` (an empty `entries` list loads), but once `rules/config.yaml` exists it also needs `notices.yaml` with every
situation wording and `rules/confirm.yaml`, `commands.yaml`, `corrections.yaml`, `confusions.yaml`. Those five are
about the language, not the business (the three domains in the repository share them word for word per language), so
the studio keeps one **language starter** per engine language in `studio_backend/starters/<lang>/` and every new bot
gets it. A new bot therefore passes validation at once and its 기본 설정 can be saved without breaking it.

**Flow**: 홈 → **새 상담봇** (header button; also the empty state) → one dialog, top to bottom:

| Part | Choice | Rules |
|---|---|---|
| 업종 | an existing business, or **새 업종**: 업종 이름 (any text, e.g. 병원 예약) and 영문 ID (`[a-z][a-z0-9-]{1,39}`, filled from the name when it is ASCII) | The ID may not be one already in the studio or a not-yet-imported folder of `domains/` (that one is offered as 가져오기 instead) |
| 언어 | the engine's languages | A language the business already has is shown disabled with "이미 있어요" (one bot per business and language, `UNIQUE(domain_id, lang)`) |
| 시작 방식 | **빈 상담봇** or **다른 언어 상담봇 복사** (only for an existing business with another language) | Copy takes the sibling of the same business; 새 업종 has nothing to copy |
| 기본 설정 | 이름, 기본 재질문 횟수, 상담사 연결 번호 | Same storage and checks as 개요 (`settings.check_engine` for the config, `check_studio_only` for the number); the rest stays on 개요 |

After 만들기 the user lands on the new bot's 개요, which says what to do next.

**What each start gives**

| | 빈 상담봇 | 복사 |
|---|---|---|
| FAQ, scenarios | none | all of the sibling's, same ids, node ids, triggers, buttons and texts (so the engine's twin test still lines up) |
| Scenario layout | none | copied (positions are not language) |
| `rules/config.yaml` | engine defaults, plus the dialog's values | the sibling's numbers, plus the dialog's values |
| notices.yaml | the starter's situation wording, no fixed notices | the sibling's fixed notices (to translate) + the starter's wording in the new language |
| confirm, commands, corrections, confusions | starter of the new language | starter of the new language (the sibling's words are in the wrong language) |
| hand-off number, 정책값 | the dialog's number | the sibling's, then the dialog's number |
| Shared assets (API 연결, 속성 종류) | shared with the business as they are | same |
| Not copied | | evaluation cases (`scenarios/`) and `faq_unanswerable.yaml`: test data written in the sibling's language |

**번역할 곳**: a copy remembers what still holds the sibling's language in `bot.origin` (new column, migration 0004):
`{copied_from, to_translate: {faq: [ids], flows: [ids], notices: [ids]}}`. Saving an FAQ entry or a scenario takes it
off the list (deleting too); 개요 shows the remaining count with links and **모두 번역했어요** to clear it. The FAQ list
and the scenario list tag each item **번역 필요**. Validation does not look at it: the engine does not know the language
of a sentence.

**Empty bot guidance**: 개요's next step for a bot with no FAQ and no scenario is "질문이나 시나리오를 하나 추가해
보세요" with both links; 대화로 테스트 on such a bot opens with a note that every sentence will get the situation
wording `flow.no_flow` (그 부분은 도와드리기 어렵습니다) until something is added (it still runs, so the wording can be heard).

**API**: `GET /languages` (engine `LANGS` with display names left to the client), `POST /bots`
`{domain, domain_title?, lang, title?, start: "empty" | "copy", copy_from?, settings?: {engine?, studio_only?}}` → `201`
bot; `409 {reason: "exists" | "in_repo"}`, `422` for a bad ID, language, copy source or setting. `PUT /bots/{b}/translation`
`{faq, flows, notices}` sets what is left to translate. Bot rows gain `domain_title` and `to_translate` (count).

Built as above. Checked on 5710: 새 업종 병원 예약 (`clinic`) in Korean as an empty bot, 검증 passed and 대화로 테스트 answered
with `flow.no_flow`; after one question and one scenario were added, the English bot was made as a copy (Korean disabled, the
hand-off number taken from the sibling), 개요 listed 번역할 곳 2개, the FAQ list opened on 번역할 질문, and saving the
translated question took it off. Not done: fixed notices to translate cannot be edited on
screen until the ST3 안내 문구 screen exists (the card says so).

### 상담봇 삭제 (owner request, 2026-10-30)

At the bottom of 개요, a 상담봇 삭제 band (red outline, out of the way of the form). The dialog lists what goes, from
`GET /bots/<b>/delete-impact`: the FAQ and scenario counts with the defaults, the publications and the files the engine
read (`studio/exports/<bot>/`), and, when it is the domain's last bot, the domain itself with its API 연결 and 속성 종류.
삭제 stays disabled until the bot's name is typed, because nothing can be undone (a repository domain can be imported
again). Then the home page and a toast. A copy whose source is deleted keeps working; its 번역할 곳 card keeps the
source's language name. Checked on 5710: the English 병원 bot, then the Korean one, which took `clinic` with it.

