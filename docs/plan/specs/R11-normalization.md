# Spec R11: normalisation of numbers, dates and times (C07)

Read first: this file, [queue.md](../queue.md), decision sheet rows R11-1 to R11-3, R3-1, R4-2, R7-12,
`docs/flow-spec.md`, `voxstage/rules/flows.py`, `voxstage/rules/interpreter.py`, the C07 scenario files, and the turns
of C02, C05, C06 and C08 that are spoken numbers (they show what the extractors must read).

## Decisions already made (do not reopen)
- R11-1: written in this repo for English and Korean, only the subset the dataset needs, as a self-contained module
  `voxstage/normalize/` (pure functions, no import from the rest of `voxstage`, so it can later become its own
  package); no library; table-driven tests.
- R11-2: dates resolve against the scenario clock (`setup.now`, in `state.meta["now"]`) with fixed rules written to
  `trace`: a day without a month, or a month and day without a year, is the nearest date not in the past; Korean
  "다음 주 X요일" is that weekday of the next calendar week. Only an English "next / this + weekday" whose weekday
  still lies ahead in the current week is asked, with both dates (`date.ambiguous`, answer by a date or keypad 1 / 2,
  the ask re-prompt policy).
- R11-3: tools `schedule_transfer` [amount, date, to_account], `schedule_delivery` [quantity, delivery_date,
  delivery_window], `change_bill_date` [bill_day, effective_from], all `risky: true`; flows capture, ask what is
  missing, confirm, call.

## Build
1. `voxstage/normalize/` (`en.py`, `ko.py`, `dates.py`, `__init__.py`):
   - `numbers(text, lang)`: every number in the text, in order, as integers: digits ("2,500"), English words
     (zero to nineteen, tens, hundred, thousand, "twenty five hundred" = 2500), Korean Sino-Korean numerals
     (일 ... 구, 십, 백, 천, 만: 삼십, 십오, 이천오백) and Korean native numerals only right before a counter
     (두 개, 세 명: 개, 명, 장, 대, 권, 벌), so "네" (yes) is never four. A run of two or more single digits said one
     by one ("four eight two one", "사 팔 이 일", "one five", "일 오") is one number read digit by digit.
     Numbers that belong to a date or a day of the month are not returned.
   - `digit_string(text, lang)`: the digits of a number said digit by digit, or written, as a string (keeps zeros).
   - `day_of_month(text, lang)`: "the twentieth", "20th", "이십 일", "20일" -> 20 (in a day phrase a trailing 일 is
     the day suffix: 이십일 -> 20).
   - `date(text, lang, now)`: today / tomorrow / the day after tomorrow (오늘, 내일, 모레), "the fifteenth of next
     month" / "다음 달 십오일", month names with a day ("November fifteenth", "십일월 십오일"), a bare day, weekdays
     with this / next (이번 주, 다음 주). Returns an ISO date, an `Ambiguous(first, second)`, or None. The rule used
     goes into the result for `trace`.
   - `month_start(text, lang, now)`: the first day of the month referred to ("next month", "다음 달부터",
     "November") as an ISO date.
   - `time_window(text, lang)`: morning / afternoon / evening (en morning, afternoon, evening, night; ko 오전, 아침
     -> morning, 오후 -> afternoon, 저녁, 밤 -> evening).
   - Table-driven tests in `tests/test_normalize.py`.
2. Extractors (`flows.py`, `interpreter.py`): `number` returns the first number of `numbers`; `digits` also accepts
   a number said digit by digit (keypad-only slots still refuse speech, R3-1); new extractors `date`, `month_start`,
   `day`, `time_window`; captures may use them. `extract` gets the clock from `state.meta["now"]`; a `date` or
   `month_start` extractor without a clock is a missing attribute (R4-2: apology and hand-off).
3. Ambiguous dates (R11-2): at an `ask` with the `date` extractor an `Ambiguous` result is not a value and not a miss:
   the reply is the registry wording `date.ambiguous` followed by the two dates (written with the `date` formatter)
   numbered 1 and 2, the candidates are kept in `state.meta`, and the next answer is keypad 1 / 2 or a date equal to
   one of them; anything else follows the ask re-prompt policy. `date.ambiguous` becomes a required wording key.
4. Content (twins): the three tools and flows of R11-3; the flows capture all their slots from the first words.
5. `docs/flow-spec.md`: the new extractors, the clock, the ambiguity rule.

## Done when
- C07 base scenarios pass in all three domains and both languages.
- Bank C08 passes in both languages and bank C02 in English (Korean bank C02 stays failing, R7-9).
- Earlier results hold; every regression is listed in the handoff note. NullDM 0 and OracleDM 100 percent.
- Tests: the normalisation tables (each function, both languages), the yes word 네 is not a number, digit-by-digit
  numbers, dates against the clock with the rule in the result, the ambiguous English weekday asked and answered
  both ways, a date extractor without a clock, the three flows confirming before their calls.

## Metrics for the handoff note
C07 pass counts (base, variants, noisy) per domain and language; overall pass counts; lines of `voxstage/normalize/`
(counted separately from the interpreter); number of normalisation table rows; earlier cases fixed or broken.
