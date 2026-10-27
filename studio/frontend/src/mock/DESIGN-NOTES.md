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

## Skills used

`claude-mem:design-is` (audit table above) and the `dataviz` rules for the home summary tiles. The newly installed `frontend-design`, `Design` and
`design-skills` plugins are not in this session's skill list (they load at session start); the later implementation steps
should use them where available.
