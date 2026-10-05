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

Approved as is (no change planned): the Korean C09 fixed notices for bank, shop and telecom.
