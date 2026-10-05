# 0007. A Korean dataset is added alongside the English one

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

[ADR 0006](0006-english-first.md) made English the first language and deferred Korean. The
owner now wants Korean cases as well, because the owner reviews and gives feedback on Korean
far more reliably than on English. Review by the owner is the gate for every capability
(see [dataset-spec.md](../dataset-spec.md)), so a dataset the owner cannot judge well weakens it.

## Options considered

1. **Add `ko/` next to `en/`**, same ids, English kept as is.
2. **Replace English with Korean**: loses the English twin that the English ASR/TTS runs need.
3. **Keep English only and review through translation**: the owner reviews a second-hand text.

## Decision

We will add a full Korean dataset under `domains/<domain>/ko/` and keep the English one.
Both languages are developed in parallel. Korean cases are *twins*, not translations: same
ids, capability, setup, `flow`, `slots`, `tool_calls` and `actions`, but the utterances,
expected wording, variants and hand-written ASR errors are written as a Korean caller would
produce them. A test enforces the twin rule.

## Rationale

- The decider's reason: Korean is the language the owner can give better feedback in.
- Twin ids keep results comparable across languages (the idea behind MASSIVE below).
- Korean exposes problems English hides: number readings (삼십/십삼, 이천오백 달러),
  relative dates (담달 보름), particles, word spacing and homophone recognition errors.

## Public basis

- [MASSIVE (FitzGerald et al., 2022)](https://arxiv.org/abs/2204.08582): one intent and slot
  structure carried across 51 languages with aligned ids.
- No public source was found for the Korean-specific wording; it is hand-written and has not
  been checked against real Korean ASR output.

## Consequences

- 72 Korean cases (8 FAQ + 16 scenarios per domain, three domains), checked by the same
  integrity tests as English, plus a test that Korean and English twins agree on structure.
- `tools.yaml` stays shared and in dollars, so Korean callers say 달러 or 불.
- Slot values are shared too, so a Korean ASR error must produce the same wrong slot as the
  English one (C05: 삼십 heard as 십삼 gives "13"). A digit-order swap is a weaker Korean
  error than the English one.
- Review effort doubles for any later change to a case.

## Open questions

All four open points were answered by the decider on 2026-10-05 and are collected in
[data-enhancement-backlog.md](../plan/data-enhancement-backlog.md), to be handled together
after S3:

- Currencies: major currencies (dollar, won, yen, ...) should each be supported (D1).
- Korean ASR errors: classify error types for Korean itself (D2).
- Bot-response wording: revise after real bot replies exist (D3).
- Korean-only cases: same stage as the currency work (D4).

The Korean C09 fixed notices were reviewed and approved as written.

## Decider's note

"한글 데이터셋이어야지 내가 더 잘 피드백 줄 수 있을것 같아. 기존영어 놔두고 한국어 데이터셋을 추가해서 진행해줘"

On review of the Korean draft (2026-10-05): currencies, the Korean ASR error types and Korean-only
cases wait for a joint data-enhancement stage after S3; the C09 notices are fine; bot-response
wording is revised once a bot answers.
