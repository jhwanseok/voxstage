# Data enhancement backlog (revisit after S3)

Decided by: jhwanseok, 2026-10-05. Items below are known weaknesses of the current datasets.
They are collected here on purpose and fixed together in one data-enhancement stage after S3,
instead of patching the data piecemeal while the rule engine is being built.
Until then the current data stays as it is. Each item names where it came from and what "done" means.

| # | Item | Why it waits | Done when |
|---|---|---|---|
| D1 | **Currencies**: support the major currencies (dollar, won, yen, ...) instead of USD only. `tools.yaml` is shared by both languages, so this is a shared tool-spec change plus new or adjusted cases. | Touches every domain and both languages; better done once. | Each language can run with its natural currency; the amount cases (C07, C08, C12) have a currency dimension. |
| D2 | **Korean ASR error taxonomy**: classify error types for Korean on their own terms (for example sound-alike syllables, number readings, word spacing, particle or ending changes, homophones), not by copying the English error types. C05's current Korean error (삼십 heard as 십삼, a digit-order swap) is a placeholder. | Needs a public basis for the categories and may need twin slots to be relaxed so Korean can produce its own wrong values. | A written taxonomy with sources, and Korean ASR variants and C05 rewritten against it. |
| D3 | **Bot-response wording**: the expected reply keywords (`reply_contains*`, `reply_not_contains`) were guessed before any bot existed, for example "배송 중", "다시 입력", "열흘". Number-only forbidden strings miss other readings ("오십 불"). | Can only be judged against real bot replies. | Keywords revised after the rule engine's first replies exist; each revision is logged in the effort ledger. |
| D4 | **Korean-only cases**: native-Korean numerals (열흘), counter words, honorific mismatch, and similar. | Same stage as D1 and D2; new ids, not twins. | New cases with their own ids, reviewed by the owner. |
| D5 | **Past dates**: cases where a date means the past ("the transfer I sent on the 15th", "지난주 화요일에 주문한 거") and a flow that takes one (a transaction or order lookup). The `date` extractor then needs a per-slot direction (`past` / `future`) and past words (last, yesterday, 지난, 어제) (decision R11-6). | No flow takes a past date yet; every dated flow is about the future. | Cases in both languages and the direction option, with the R11-2 rule kept as the future default. |
| D6 | **Sign-in methods**: cases only use a PIN (bank, telecom) or a ZIP code (shop). Real services also sign callers in by phone number plus date of birth, a one-time code sent by text, a card number plus expiry, or caller ID (decision R13-3). | The R13 verification steps are declared per domain, so a method is a content change; cases wait for the data stage. | Cases in both languages for at least one other method (phone number plus date of birth, with a date-of-birth extractor), including a partial match that must not reveal which part was wrong. |
| D7 | **API delay and risky timeouts**: C10 has only timeouts of lookups. Add cases with a slow answer (`delay_ms` past `timeout_ms`), a risky tool that times out (outcome unknown, hand-off, R12-3) and two failures in one call (R12-4). | The engine handles them since R12; the cases wait for the data stage. | Cases in both languages for the three kinds. |

Approved as is (no change planned): the Korean C09 fixed notices for bank, shop and telecom.
