# 0005. Datasets come first; capabilities are built one problem at a time

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

The project compares rule-based, LLM and agent stages on realistic service problems. A fair
comparison needs the same cases for every stage, written before any stage is built.

## Options considered

1. **Dataset first**: write cases for every capability and domain, then build capabilities
   one at a time against them.
2. **Build then test**: write cases as each capability is implemented.
3. **Dataset format**: YAML scenario files, or JSONL.

## Decision

We will write the datasets first: 13 capabilities (C00 FAQ baseline plus C01 to C12) across
three domains, bank, shopping mall and telecom. Each case is a YAML scenario or FAQ entry
(see [dataset-spec](../dataset-spec.md)). Development starts at STT, FAQ, TTS (C00) and then
adds one capability at a time, each judged against its cases.

The authoring order is: Claude drafts a pilot slice, the owner reviews and edits it, and the
approved shape is then expanded. The owner makes the final call on case content.
Cases are synthetic and written from scratch; no employer scenario is used or adapted.

## Rationale

- Same cases for all stages is what makes the stage comparison meaningful.
- Each capability then has a concrete failing case before its implementation exists.
- YAML is readable and diff-friendly, which suits human review; scale is modest.
- Cost accepted: an upfront authoring effort, and cases may need revising when an
  implementation exposes an ambiguity (changes to cases are recorded in git history).

## Public basis

- [Schema-Guided Dialogue (Rastogi et al., 2020)](https://arxiv.org/abs/1909.05855) and
  [MASSIVE (FitzGerald et al., 2022)](https://arxiv.org/abs/2204.08582): multi-domain
  datasets organised by domain, intent and slot annotations.
- [τ-bench (Yao et al., 2024)](https://arxiv.org/abs/2406.12045): domain tasks with
  expected outcomes, evaluated by end state rather than wording.
- No public source was found for organising cases by *capability* across domains. That
  matrix is this project's own; the S1 experiments test whether it is a useful lens.

## Consequences

- `domains/<name>/` holds `faq.yaml`, `tools.yaml` and `scenarios/*.yaml`; the core only
  reads them through `voxstage/dataset.py`.
- The plan's earlier `kb.md` becomes `faq.yaml`, so paraphrase and recognition-error
  variants are structured data.
- Recognition-error variants are hand-written at first. Real ASR noise enters in audio mode.
- `python -m voxstage.dataset coverage` prints the capability by domain matrix.

## Open questions

- Variant counts per case needed for stable statistics. Decide after the first S1 run.

## Decider's note

"먼저 12개의 기능의 대한 3개 도메인의 데이터셋을 만들꺼야. 그걸 시작으로 하나씩의 문제를 해결하면서 기능을 구현해나갈 꺼야. 처음에는 STT - FAQ - TTS 가 시작지점이 될거야."
