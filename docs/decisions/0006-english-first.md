# 0006. Datasets are English first; Korean is added later

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

The pilot dataset was first drafted in Korean. The speech components the project will use for
its first runs are English, and the owner wants the repository to be easy to extend and to
read for an international audience.

## Options considered

1. **English first, Korean later** as a parallel language directory with the same case ids.
2. **Korean first**, matching the earlier drafts.
3. **Both from the start**: doubles authoring and review effort before any capability exists.

## Decision

We will write all datasets in English first. Korean is added later under `domains/<domain>/ko/`
using the same case ids. The pilot's Korean drafts were removed from the tree; they remain in
git history (commit 68e7e5c).

## Rationale

- The decider's reason: STT and TTS are English, and English is better for extensibility.
- One language keeps review effort low while the schema and capability cases are still moving.
- Same ids across languages let a Korean case be compared against its English twin later.
- Cost accepted: Korean-specific problems (number readings, particles, spacing errors) are
  not covered until the Korean extension, so early results say nothing about Korean.

## Public basis

- [MASSIVE (FitzGerald et al., 2022)](https://arxiv.org/abs/2204.08582) is a multilingual
  dataset covering 51 languages, showing that a domain, intent and slot structure can be
  carried across languages.
- No public source was cited for the English-first choice itself; the reasoning above is
  the decider's.

## Consequences

- Layout and loader are language-aware (`<lang>/` directories, a required `lang` field).
  `tools.yaml` is shared across languages, so it holds language-independent values (USD amounts,
  grade names).
- A test fails if an English data file contains Hangul.
- Still Korean by default and to be revisited: `DEFAULT_SYSTEM_PROMPT` in `pipeline.py`,
  `data/scenarios.json` (the latency benchmark's five utterances), the ASR default
  `language="ko"`, the TTS default `language="KR"`, and the Colab notebook. The vendor
  options already accept other languages (`--asr-opt language=en`, `--tts-opt language=EN`).

## Open questions

- Which English ASR and TTS models to use for the first real run. Not decided yet.
- Whether the latency benchmark's five utterances are translated now or when the English
  vendors are chosen.

## Decider's note

"모든 시나리오가 영어로 일단 만들었으면 좋겠어. STT / TTS 모두 영어로 되어 있다보니 그리고 그게 더 확장성 측면에서 좋을것 같아. 한국어는 나중에 확장해보자"
