# 0009. FAQ rule manager: pattern language, held-out text, fallback escalation

Status: accepted
Date: 2026-10-05
Decided by: jhwanseok (options and analysis prepared with AI assistance)

## Context

Step R1 is the simplest rule engine: a question in, the verbatim answer out, a safe fallback otherwise.

## Options considered

1. Pattern language: word groups; regular expressions; both.
2. Behaviour after a miss: one generic apology forever; escalate after N misses.
3. Held-out text: only `asr_variants`; both `paraphrases` and `asr_variants`.

## Decision

1. **Word groups first** (`all_of`, `any_of`, `none_of`, priority). A regular expression is allowed only
   where a word group cannot express the rule, and the rule is logged as such.
2. **Escalate after N consecutive misses**, and N is configurable (per domain and language). What happens
   at N is also configurable: hand off to an agent or end the call. A match resets the counter.
3. **Both `paraphrases` and `asr_variants` are held out.** Rules are not written while looking at them.

## Rationale

- 1: word groups are readable and countable, so rule effort can be measured; regexes hide complexity.
- 2: the decider wants the end of a failing conversation to be a configurable policy, not a fixed apology loop.
  This moves part of R8 (hand-off) into R1.
- 3: the decider: the dataset must not be used while writing the rules. A rule author reads only the
  canonical question, the answer and the capability spec.

## Public basis

- None for hand-written keyword rules.
- [BEIR (Thakur et al., 2021)](https://arxiv.org/abs/2104.08663) supports BM25 as the baseline once
  retrieval arrives in S2; that comparison is planned there.

## Consequences

- `HandOff` and `EndCall` are used in R1; the miss counter lives in `state.meta`.
- A fresh session that reads only `question` and `answer` writes the patterns. The held-out guarantee is
  procedural; a command prints the author's view of the data without the held-out fields.
- Korean rules need a tokenisation decision (particles) and are not part of R1 (see decision sheet, item 17).

## Decider's note

"패턴언어는 얘기한대로 진행해줘" / "매칭 실패시 N번을 상담사 또는 통화종료를 선택하게 해야 하고, N번도 커스텀 할 수 있어야 해." /
"둘다 쓰는게 좋지 않을까? 다만 데이터셋이 `paraphrases`와 `asr_variants를 보고 만들어져서는 안될것 같아."
