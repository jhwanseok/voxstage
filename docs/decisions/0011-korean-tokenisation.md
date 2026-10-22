# 0011. Korean rule matching uses a morphological analyzer (Kiwi), optional dependency

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

Rule packs cover English and Korean from R1 (decision sheet D-17). Word groups (ADR 0009) assume that a word
is a token. In Korean a word carries particles and endings ("영업시간이", "되나요"), and word spacing varies
("영업시간" and "영업 시간"). Matching needs a tokenisation choice.

## Options considered

1. **Morphological analyzer (Kiwi).** What an engineer who knows Korean would use for a fair baseline.
2. **Hand-written particle and ending stripping** plus substring matching: no dependency, transparent, but weaker.
3. **Character n-grams / space-stripped substring matching**: robust to spacing and endings, low precision.

## Decision

Option 1. Kiwi is an optional dependency (`pip install voxstage[ko]`); English runs without it. Matching on
Korean text uses the content morphemes (nouns, verb and adjective stems, numerals, foreign words) and also matches a
pattern word of two or more syllables as a substring of the space-stripped joined content morphemes, so
"영업시간" and "영업 시간" match the same pattern.

## Rationale

- The decider chose it from the three options after reading them. The assistant's reasons: option 2 risks a
  strawman baseline (the project's fairness rule), and option 3 makes rule effort hard to count.
- Tried before deciding: on sample sentences Kiwi splits "영업시간이" into 영업시간 + 이 (particle) but "영업 시간이"
  into 영업 + 시간 + 이, which is why the space-stripped match is added.

## Public basis

- Kiwi's own repository documents it as a Korean morphological analyzer released under LGPL v3
  (<https://github.com/bab2min/Kiwi>). The licence of the `kiwipiepy` wrapper package was not stated on that page and
  must be checked in its repository before release.
- No public source for the space-stripped matching rule; the experiment in this repo validates it.

## Consequences

- LGPL v3 is not the Apache-2.0 of this repo; an optional, separately installed dependency is the intended
  boundary. The owner confirms the licence position before a release to `main`.
- Korean patterns are written over lemmas and nouns, not surface forms.
- ASR errors that break analysis (a misheard syllable) show up as misses; that is measured, not hidden.

## Open questions

- Whether other analyzers are compared later (as an experiment, not a baseline change).
- Interjections are kept for yes or no answers only; see the amendment below.

## Amendment 2026-10-22: yes and no answers keep interjections

Kiwi tags 네, 예, 응, 아니요 and 아뇨 as interjections (`IC`). The content morphemes above do not include interjections,
so a Korean caller answering a confirm node (R7-12) with "네" or "아니요" produced no token and could never match.
Rule matching (FAQ patterns, flow triggers, interrupts, slot extraction) keeps the content morphemes as decided above.
Only the analysis of a yes or no answer at a `confirm` node also keeps interjections
(`Tokenizer.analyze_answer`; for English it is the same as `analyze`).
Decided by jhwanseok (asked for this amendment on 2026-10-22 after the R7b handoff note raised it).

- Why not add interjections everywhere: it would change the tokens of every FAQ query and trigger, and so the R1
  numbers, for a problem that only exists at yes or no questions.
- Public basis: none found; this repo's own test validates it (`tests/test_confirm.py`,
  `test_korean_yes_and_no_are_interjections_kept_for_answers`: `analyze("네 맞아요")` gives `맞`, `analyze_answer`
  gives `네 맞`).
- Known consequence of the same rule, left as it is (decision R7-9): dependent nouns (`NNB`, for example 시 in
  "몇 시까지") are dropped too, so a pattern word such as `몇시` can never match.

## Decider's note

Chose "형태소 분석기 Kiwi" from the three options.
