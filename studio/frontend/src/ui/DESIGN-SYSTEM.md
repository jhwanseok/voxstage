# Studio design system

Made with the `design:design-system` skill (extend mode) on top of the approved mockups (`src/mock/`, notes in
`src/mock/DESIGN-NOTES.md`). Tailwind v4 for styling, shadcn/ui-style primitives (the source lives in `src/ui/index.tsx`,
no component library at run time), lucide for icons. The direction (white ground, one indigo accent, rounded cards)
stays as the owner approved it; what changed is that every value is now a token and every list has its states.

## Tokens (`src/styles.css`)

Components use the semantic names only (`bg-surface`, `text-muted`, `border-line`, `bg-ok-bg` ...); light and dark are
switched in one place under `prefers-color-scheme`.

| Token | Light | Dark | Use |
|---|---|---|---|
| `ground` | #f6f7f9 | #0f1218 | page background |
| `surface` | #ffffff | #161a22 | cards, panels, inputs |
| `sunken` | #f1f3f6 | #1c212b | table heads, quiet blocks, hover |
| `line` / `line-strong` | #e3e7ee / #8a94a6 | #2a313d / #636d7e | dividers / input borders (3:1) |
| `ink` / `ink-2` / `muted` | #101828 / #475467 / #5d6b82 | #e8ebf1 / #b4bdcc / #96a1b3 | text: primary, secondary, hints |
| `brand-50 … 700` | #eef0ff … #3a3ab3 | #23264a … #b9bcff | one accent: primary action, selection, focus |
| `ok / warn / err / idle` `-fg -bg -line` | emerald / amber / rose / slate | dimmed | status chips, notices |
| `canvas`, `canvas-dot`, `edge` | #f2f3f7, #d9dde6, #8a94a6 | dark | scenario canvas |

Contrast (WCAG 2.2 AA, computed): ink 17.8, ink-2 7.7, muted 5.4 on surface and 4.9 on sunken; white on brand-500 5.95;
brand-700 on brand-50 7.6; ok 5.2, warn 4.8, err 5.7, idle 6.9 (fg on bg); input border 3.1. Dark: all text pairs
6.7 to 14.6, white on brand 5.1, border 3.0.

Type: Pretendard Variable (CDN, falls back to Noto Sans KR / Malgun Gothic). Scale 12 / 13 / 14 / 15 / 18 / 20, weights
400, 500, 600, 700; counts use tabular numbers (`.num`). Spacing on a 4 / 8 grid; radius 6 (controls), 8 (chips,
menus), 12 (cards), 16 (forms, dialogs). Motion: only in answer to an action (sheet, menu, toast), none idle, off under
`prefers-reduced-motion`.

## Components (`src/ui/index.tsx`)

| Component | Variants / props | States | Keyboard and screen reader |
|---|---|---|---|
| `Button` | primary, secondary, ghost, danger; sm, md; `icon`, `loading` | hover, disabled, loading (spinner, `aria-busy`) | native button |
| `IconButton` | `label` required | hover, disabled | `aria-label` = label |
| `StatusChip` | ok, warn, err, idle, brand | always icon + text (never colour alone) | text read as is |
| `Tag` | tone | – | words inside content |
| `Notice` | tone, `title`, `action` | `role="alert"` for err | – |
| `Field` + `Input` / `Textarea` / `Select` | `label`, `hint`, `error`, `optional`, `aside` | invalid (`aria-invalid`, red border, message with icon) | label `for`, hint and error in `aria-describedby` |
| `WordsInput` | tone | focus ring on the box | Enter or comma adds, Backspace removes last, each tag has a labelled remove button |
| `Segmented` | options with counts | selected | `radiogroup` / `radio` + `aria-checked` |
| `Disclosure` | `title`, `summary` (shown closed), `badge` | open / closed | `aria-expanded`, `aria-controls` |
| `Sheet` | `title`, `subtitle`, `footer`, width | – | `role="dialog"`, `aria-modal`, focus trapped, Esc closes, focus returns |
| `Dialog` | same, centred | – | same |
| `LoadingBlock`, `Skeleton` | rows | shimmer (off with reduced motion) | `role="status"` + label |
| `EmptyState` | icon, title, text, action | – | – |
| `ErrorState` | error, `onRetry`, what | – | `role="alert"`, retry button |
| `ToastProvider` / `useToast` | tone | auto-hides after 4 s | one `aria-live="polite"` region |
| `PageHeader` | title, count, description, actions | – | the page's one `h1` |

## Patterns

- **One screen, one task.** Lists are full width; editing opens in a `Sheet` over the list (FAQ, API) or in the side panel
  of the canvas (scenario). The overview holds one form with one save bar.
- **Every list has four states**: loading (`LoadingBlock`), empty (`EmptyState` with the first action), error
  (`ErrorState` with retry), filtered-empty (one sentence on how to widen the filter).
- **Save bar**: says whether there are unsaved changes and what happens next (validate, publish); buttons are
  되돌리기 / 저장, the primary one disabled until something changed. Leaving with unsaved changes asks first.
- **Status words** follow the order the user acts in: 고칠 곳이 있어요 → 검증이 필요해요 → 게시하지 않은 변경 → 게시됨.
- **Internal names** (file names, node ids, slot names) appear only under 개발 정보, in a monospace face.
- **Addresses**: every link and redirect goes through `src/paths.ts` (absolute paths only; see the URL bug in DESIGN-NOTES).
