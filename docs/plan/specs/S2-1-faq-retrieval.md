# Spec S2-1: FAQ retrieval with embeddings (C00), compared with S1

Status: draft, **needs decisions** S2-4 to S2-7 (decision sheet, "S2 decisions"). Nothing is built before they are
recorded. Read first: [decision-sheet.md](../decision-sheet.md) rows S2-1 and S2-3, [R1](R1-faq-rule-manager.md)
(held-out rule), [stage-comparison.md](../../stage-comparison.md), `voxstage/rules/faq.py`, `voxstage/evaluate.py`.

## Goal

Answer the FAQ questions of C00 by similarity search over sentence embeddings instead of keyword rules, and put the
result next to S1 in the stage comparison: same cases, same split, same modes. Slot extraction and dialogue state
tracking are not in this item (S2-2).

## Already decided

- S2-1: the first S2 build covers FAQ retrieval only, compared with S1 on C00.
- S2-3: start with `multilingual-e5-small` (local, CPU). `bge-m3` is a separate comparison row, not the first build.
- S1 is closed (R15-2): the S1 numbers do not change. C00 in S1: 89/144 and 89/144 (en clean/noisy), 86/149 and
  86/149 (ko clean/noisy).
- The held-out rule of R1 holds for S2 as well (see below).

## What is compared

The cases are the ones `voxstage/evaluate.py` already builds for C00: per FAQ entry the canonical question, its
paraphrases and its ASR variants, in three domains and two languages (144 en, 149 ko), in clean and noisy mode, plus
the unanswerable draft list (five questions per domain and language) for false accepts.

Reported, not averaged across languages:

| Measure | Where |
|---|---|
| top-1 accuracy on canonical questions, paraphrases and ASR variants, separately | stage-comparison S2 column (C00) |
| false accept on the unanswerable draft list (a draft, "not reviewed by the owner" as in S1) | beside it |
| the same two numbers at several thresholds (a sweep), shown as a table; the threshold used for the headline number is fixed before the first C00 run | spec appendix of the run report |
| miss, escalation and fallback wording | unchanged from S1 (same `fallback` config, same counter `faq_misses`) |

Pass rate in the stage table is the C00 cell as in S1: a case passes when the verbatim answer of the right entry is
the reply.

## Design (proposal, to be confirmed by S2-4 to S2-7)

- **Port.** `FaqRetriever` with `match(text) -> (entry | None, trace)`, the same signature as the S1 matcher, so the
  flow interpreter's waiting-ask logic (an FAQ side question before an answer is read, R7-4) works with either.
  `FaqRuleManager` takes the matcher as a parameter; `FaqEmbeddingManager` is a sibling with the same `respond`.
- **Index.** Built when the domain pack loads: one vector per indexed text, normalised, stored in memory (numpy). A
  few dozen texts per language, so exact cosine search; no vector database.
- **Query.** The utterance text as the dialogue manager sees it (noisy mode feeds the ASR variant). The model's
  documented input prefixes (e5 expects `query: ` on the query and `passage: ` on the indexed text) are applied in
  one place and covered by a test.
- **Decision.** Best cosine similarity `s1`; accept when `s1 >= threshold` and, if S2-6 says so, `s1 - s2 >= margin`.
  Otherwise the S1 fallback path (miss counter, hand-off).
- **Dependency.** Optional extra `retrieval = ["sentence-transformers"]` in `pyproject.toml` (like `ko`), imported
  lazily; the model is not in the repository. Tests that need the model use `unittest.skipUnless` and the report says
  "skipped, model missing", never a silent pass.

## Open questions (asked one at a time; each has a recommendation in the sheet)

| ID | Question | Recommendation |
|---|---|---|
| S2-4 | How embeddings and rules combine. | Measure two configurations: embedding only (the clean S2 row, comparable with S1) and rules first, embedding when no rule matches (the practical one). Score fusion is not built. |
| S2-5 | What is indexed. | The canonical `question` of each entry only. Not the rule patterns (word groups are not sentences), not `paraphrases` or `asr_variants` (held out). Extra example questions an operator writes later are a separate feature. |
| S2-6 | Threshold, margin and the reject policy, and what they are calibrated on. | A frozen calibration file `domains/<d>/<lang>/faq_calibration.yaml`, written once before the first C00 run (about ten new in-scope paraphrases and ten out-of-scope questions per domain and language, wording not copied from the held-out fields), is the only data a threshold or margin may be chosen on. The chosen values and the file's hash go in the run report. |
| S2-7 | How the comparison with S1 is judged and what "better" means. | Report the pair (accuracy, false accept) at the fixed threshold and the sweep. No single score; a result is "better" only if it is not worse on false accept. |

## Rules for the build (do not reopen)

1. **Held-out.** `paraphrases`, `asr_variants`, scenario `variants` and `asr_text` are never an input to indexing,
   threshold choice, prompt or prefix choice, or model choice. They are read only by `evaluate`. Reading failures
   after the first run is allowed (as in R1); a change after it must come from the calibration data or the capability
   spec, and the number of changes after the first run is reported.
2. **One headline run per configuration.** The model, prefix, threshold and margin are fixed before the first C00 run.
   Any later change is listed with the reason in the run report.
3. **bge-m3** runs the same code with another model name, the same threshold procedure (calibrated again on the
   calibration file), and is reported as a separate row.
4. **No network in tests or evaluation.** The model is downloaded once by an explicit command
   (`python -m voxstage.retrieval download <model>`), never by an import or an evaluation run.

## Measurements

- Latency per query on CPU: p50 and p95 over all C00 queries, cold model load time separately.
- Memory: resident set size after loading, and the on-disk size of the model.
- Index build time per pack.
- Model download size (from the model cards, to be checked at download time, not downloaded in the spec step):
  `multilingual-e5-small` about 0.47 GB in fp32 weights (about 118 M parameters); `bge-m3` about 2.3 GB (about
  568 M parameters). `sentence-transformers` brings `torch`, which is the larger install; an ONNX runtime route is a
  possible later reduction, not part of this item.

## Ledger

A row per domain and language for step `S2-1` through `python -m voxstage.ledger S2-1`: patterns 0, regexes 0, plus the
new facts in the run report: model name, model size on disk, indexed texts, calibration items, p50 and p95 latency,
resident memory. If the ledger table lacks columns for them they are added once, with the old rows filled with `-`.

## Done when

- Decisions S2-4 to S2-7 are recorded in the sheet.
- `FaqEmbeddingManager` passes the same C00 harness as S1; the S2 column of C00 in the stage comparison is filled for
  both languages, clean and noisy, with the pair (accuracy, false accept), the sweep and the measurements.
- Tests: index and prefix handling, threshold and margin decision on a stub embedder (no model), the S1 fallback
  counter with the embedding manager, `match` signature parity, the held-out files not read by the build code (a test
  that greps the retrieval module for the field names), skip behaviour without the model.
- `NullDM`, `OracleDM` and every S1 result unchanged; the full suite passes without the optional model installed.
- The run report lists what the embeddings got wrong that the rules got right, and the reverse, as findings.

## Stop and report

- If a measurement would need the held-out fields to choose something, stop that part and note it.
- If the model cannot be downloaded or run on the owner's machine, report it with the error; do not switch model.
