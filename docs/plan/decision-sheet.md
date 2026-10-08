# Decision sheet for the rule-engine steps (R0–R15)

All open decisions of [rule-engine-steps.md](rule-engine-steps.md) on one page, so they can be answered
in one sitting. Each row has the assistant's recommendation. Answer with `OK` to accept it, or write
your own choice and reason (your words are copied into the decision record).
Rows marked **later** cannot be answered yet because they depend on results of earlier steps.

Decided by: jhwanseok. Nothing in this sheet is a decision until the Answer column is filled in.

| ID | Question | Recommendation | Answer |
|---|---|---|---|
| R0-1 | How a manager gets tools and scenario setup: constructor arguments (`tools`, domain pack) with `setup` copied into `state.meta`, or passed on every call. | constructor plus `state.meta`, consistent with the stateless contract. | A (ADR 0008) |
| R0-2 | Whether `slots` comparison is exact string match or after light normalisation. | exact, because normalisation is a capability (C07) being measured. | exact after a light canonical form: currency symbols/words and thousands separators ignored (ADR 0008) |
| R0-3 | What counts as a *reactive* rule and who labels it. | the owner labels it at commit time with a tag in the ledger. | dropped: no reactive label, every rule counts the same (ADR 0008) |
| R1-1 | Pattern language: word groups (as above), regular expressions, or both. | word groups first; regexes only when a word group cannot express the rule, logged as such. | as recommended (ADR 0009) |
| R1-2 | Fallback behaviour: one generic apology, or a counter that escalates to a hand-off after N misses (the latter overlaps with R8). | generic reply now, escalation in R8. | changed: escalate after N misses, N configurable, action configurable: hand off or end call (ADR 0009) |
| R1-3 | Whether the authored patterns may look at `asr_variants` while writing. | no, they are held out. | changed: both `paraphrases` and `asr_variants` held out (ADR 0009) |
| R2-1 | Schema shape: a node list with implicit order, or a state-machine map with explicit transitions. The map is more verbose but makes jumps (R6 to R8) explicit. | state-machine map with explicit transitions: more verbose, but jumps (R6 to R8) and reachability checks stay explicit. | state-machine map (ADR 0010) |
| R2-2 | Template language: Python-style `{}` fields only, or a small expression language. | `{}` fields only; conditions live in `branch` nodes. | changed: `{}` fields plus a small expression language; `branch` nodes stay (ADR 0010) |
| R2-3 | How node types dispatch: registry of handlers, `match` statement, or a class per node. Affects the design-patterns record; the assistant presents the three with a short code sketch. | registry of handlers keyed by node type, so a later step adds a node type without touching core code (the step's done-criterion). | registry (ADR 0010) |
| R2-4 | Where validation of a flow happens (load time, with node reachability checks). | load time. | load time (ADR 0010) |
| R3-1 | Spoken input at a keypad prompt: accept it, ignore it, or re-prompt. | accept a spoken value through the same extractor, because real callers do it. | Decided 2026-10-08: accept spoken values by default (A). For personal-information attributes (birth date, phone number and similar) the prompt is keypad only (C): a spoken value is not accepted, the bot asks the caller to use the keypad. The owner's words: "기본적으로 받아들이는데, 개인정보 관련 속성이라면 C로 받아야 돼. 예를들어 생년월일, 전화번호 등". Consequence: `ask` needs a per-node keypad-only setting (or a sensitivity class on the slot); Declaration decided 2026-10-08 (B): a per-domain list of sensitive slots (e.g. `sensitive_slots: [birth_date, phone_number]`), so any flow that asks for them is keypad only and the set is auditable in one file. Load-time validation must reject an `ask` for a sensitive slot that does not use keypad input. File location and name are for the R3 spec. |
| R3-2 | Invalid keypad input: re-prompt count before escalation. | two, then hand off (needs R8). | Decided 2026-10-08 (A): two re-prompts, then hand off on the third invalid input. The count and the action (`handoff` / `end_call`) are configurable and reuse the FAQ fallback's `on_exceed` setting, so no new concept. For R3 only the `HandOff` action is emitted. Open: whether a spoken answer at a keypad-only prompt counts toward the re-prompt count (recommended: yes). |
| R4-1 | Number formatting for speech: digits (`$1,250`), words, or both options in the template language. | a formatter per type (`money`, `date`, `count`) chosen in the template, so the choice is data. |  |
| R4-2 | Missing attribute: ask the caller, use a default, or fail. | fail visibly, never default silently. |  |
| R5-1 | Where notices live: a registry file (recommended) or inline in flows. A registry makes "which notices can ever be spoken" auditable. | registry file, so the set of notices that can ever be spoken is auditable. |  |
| R5-2 | Order when several notices apply, and whether a notice may be interrupted. | fixed priority list, never interrupted. |  |
| R6-1 | Abandon versus park on switch. | park, so R7 builds on it. |  |
| R6-2 | Which slots carry over (none, shared names, declared). | declared carry-over only. |  |
| R6-3 | Conflict when two interrupts match. | priority, then specificity, logged in `trace`. |  |
| R7-1 | Which things may interrupt a flow: FAQ only, or also other flows. | FAQ now, flows via R6. |  |
| R7-2 | What happens to a half-filled slot on digression. | kept. |  |
| R7-3 | Stack limit and what is said when exceeded. | limit of two nested side questions; beyond that, answer briefly and say the current task comes first. |  |
| R8-1 | `back` semantics: previous node, or previous question. | previous question. |  |
| R8-2 | When the system volunteers a hand-off (N failures, N corrections). | configurable per domain pack. |  |
| R8-3 | What survives `cancel`: nothing, or customer attributes only. | customer attributes survive `cancel`; slots and flow state are cleared. |  |
| R9-1 | When to confirm: every slot, risky slot types only, or only after a flag. In text mode there is no ASR confidence, so the choice cannot use one. | confirm slot types declared `risky` (amounts, digits). |  |
| R9-2 | Whether the confusion table is authored by hand or derived. | by hand, counted in the ledger. |  |
| R9-3 | Behaviour when the correction itself looks wrong. | ask one confirmation question (did you say X?) instead of silently accepting; if still unclear, hand off (R8). |  |
| R10-1 | Extraction method: gazetteers and regex, or small pattern grammars. | gazetteers plus regex. |  |
| R10-2 | Which references to support. | only the ones the dataset needs, and list the rest as findings. |  |
| R11-1 | Write it or use a library (`dateparser`, `word2number`). A library saves effort but adds dependencies and behaviour the repo does not control. | write the small subset the dataset needs, note what a library would add. |  |
| R11-2 | Ambiguity policy for dates such as "next Tuesday". | ask rather than guess. |  |
| R12-1 | Retry count and whether the caller is told. | retry once silently, then tell. |  |
| R12-2 | Fallback wording: generic or per tool. | per-tool wording with a generic default. |  |
| R13-1 | Granularity: per flow, per node, or per tool. | per tool, because that is where leakage happens. |  |
| R13-2 | Lockout rule and what is said. | three failed attempts, then lock and hand off, with neutral wording that does not reveal which part was wrong. |  |
| R14-1 | Whether to include the hard-coded variant as a deliberate counter-example. | yes, it is the point. |  |
| R14-2 | Which change to simulate beyond the shipped v1 to v2 pairs. | one threshold change (a fee amount) to show how many rules a different kind of change touches. |  |
| R15-1 | Which interactions to include. The assistant proposes a list with the reasoning for each. | (none given: the assistant will propose options when asked) | **later** |
| R15-2 | Whether S1 is declared finished or reactive rules continue. | (none given: the assistant will propose options when asked) | **later** |


Open details raised on 2026-10-05 (the run uses the default unless you change it):

| ID | Question | Default used | Answer |
|---|---|---|---|
| D-17 | Language scope of rule packs: English only for R0 to R5 with Korean rules in a later pass, or both from R1. Korean needs a tokenisation choice (particles). | English only; Korean rule pack is a separate later step. | **both languages from R1** (decided 2026-10-05: "한국어까지 해줘"). R1 and R2 cover ko. |
| R1-4 | Korean tokenisation for rule matching: morphological analyzer, hand-written suffix stripping, or character n-grams. | morphological analyzer (Kiwi) as an optional dependency, with space-insensitive matching of noun groups. | Kiwi, optional dependency (ADR 0011) |
| D-R0 | Canonical-form lists: which currency symbols and words. | symbols `$ € £ ¥ ₩`; words dollar(s), usd, 달러, 불, won, krw, 원, yen, jpy, 엔. | |
| D-R1 | Default N for the miss counter and its default action. | N = 3, hand off. | |
| D-R2 | Expression grammar boundary. | Comparison, and/or/not, `+ - * / // %`, `in`, attribute and constant-index access, conditional expression, and calls only to whitelisted functions (`len`, `lower`, `upper`, `int`, `str`; formatters added in R4). No lambdas, comprehensions, assignments or imports. | |

Step titles: R0 = Evaluation harness (text mode) and effort ledger; R1 = FAQ with keyword rules (C00, the STT, FAQ, TTS start point without STT and TTS); R2 = Flow interpreter; R3 = Button and DTMF input (C04); R4 = Answers from attributes and API results (C08); R5 = Condition-specific fixed answers (C09); R6 = Scenario switching (C01); R7 = Side question, then return (C02); R8 = Cancel, back, hand-off (C03); R9 = Slot correction after misrecognition (C05); R10 = Many slots at once, carry-over, references (C06); R11 = Normalisation of numbers, dates and times (C07); R12 = API failure and delay fallback (C10); R13 = Identity gate (C11); R14 = Policy change (C12); R15 = Interactions and the complexity report
