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

## Skills used

Mockups: `claude-mem:design-is` (audit table above) and the `dataviz` rules for the home summary tiles.
Real screens: `design:design-system` (tokens and component table, `src/ui/DESIGN-SYSTEM.md`), `frontend-design` (direction
review: kept the approved direction, removed template tells such as middle-dot meta strings and monospace ids on cards,
and spent the one bold element on the scenario canvas, where `{slot}` placeholders are tinted inside the spoken
sentence), then `design:design-critique`, `design:accessibility-review` and `design:ux-copy` for the review pass
(findings below).
