# S2-1 run report: FAQ retrieval with embeddings (multilingual-e5-small)

Run 2026-11-02. Spec: [S2-1](../plan/specs/S2-1-faq-retrieval.md). Decisions S2-1, S2-3 to S2-7. Model
`intfloat/multilingual-e5-small` (493 MB on disk), CPU, `sentence-transformers` 6.2.0 on `torch` 2.15.0 (CPU).
The bge-m3 row was not run (see the end).

## How it was run (held-out kept)

- Indexed text: the canonical question of every FAQ entry (24 per language). `paraphrases`, `asr_variants`, scenario
  variants and `asr_text` are not read by `voxstage/retrieval.py` (a test checks the source for those names).
- Threshold and margin were chosen once, on the frozen `domains/<d>/<lang>/faq_calibration.yaml` (8 new in-scope
  questions and 8 out-of-scope questions per domain and language, written from the canonical questions only), by the rule
  "zero false accepts on the out-of-scope items first, then the most correct answers, then the larger threshold, then the
  smaller margin". Chosen values (committed in `5ebb5b3` before the first C00 run): **en threshold 0.835, margin 0.0**
  (20/24 correct, 0/24 false accepts on the calibration set); **ko threshold 0.86, margin 0.03** (9/24 correct, 0/24 false
  accepts). Calibration hash en `df30f826260b495b`, ko `d1f8791e025a5224` (a test fails if the files change).
- One headline run per configuration; nothing was changed after seeing C00 numbers. Patterns changed after the first
  run: 0 (there are no patterns). The writer of the calibration files had seen the English bank paraphrases once before
  (an earlier `head` of `faq.yaml`) and avoided that wording.
- The unanswerable list is the S1 draft (5 questions per domain and language, "draft, not reviewed by the owner").

## C00, same harness as S1: the whole flow manager with only its FAQ part replaced (clean = noisy for C00)

Pass rate on the FAQ cases (question / paraphrase / ASR variant) and false accepts on the unanswerable draft list.

| Configuration | en C00 | en question / paraphrase / ASR | en false accept | ko C00 | ko question / paraphrase / ASR | ko false accept |
|---|---|---|---|---|---|---|
| S1 rules | 89 / 144 | 24/24, 45/72, 20/48 | 0 / 15 | 86 / 149 | 24/24, 36/72, 26/53 | 0 / 15 |
| S2 embedding only | 108 / 144 | 24/24, 45/72, 39/48 | 3 / 15 | 88 / 149 | 24/24, 25/72, 39/53 | 1 / 15 |
| S2 rules first, then embedding | 120 / 144 | 24/24, 55/72, 41/48 | 3 / 15 | 107 / 149 | 24/24, 42/72, 41/53 | 1 / 15 |

All capabilities, overall (S1 = R16a numbers, unchanged): en clean 168, 187, 199 of 247; en noisy 181, 200, 212 of 247;
ko clean 158, 158, 179 of 253; ko noisy 166, 166, 187 of 253 (S1, embedding only, rules first). Outside C00 the only
change is Korean C02 with embeddings only: 4/6 becomes 2/6 (`bank.C02.001#v1.1` and `shop.C02.001` fail).

The FAQ part alone (`FaqRuleManager` vs `FaqEmbeddingManager`, no flows around it, same cases): S1 rules 100/144 (en) and
99/149 (ko); embedding only 117/144 and 94/149; rules first 133/144 and 121/149. The difference to the table above is the
flow manager: a flow trigger takes some FAQ-shaped utterances before the FAQ is asked, in S1 and in S2 alike.

## Verdict by the S2-7 criterion

Decision S2-7: a result counts as an improvement over S1 only if it is not worse on false accepts. False accepts on the
unanswerable draft list rose from 0 (S1) to 3/15 (en) and 1/15 (ko), for both S2 configurations. **So S2-1 is not judged
an improvement over S1, although the pass rate on C00 rose** (en 89 to 120 and ko 86 to 107 with rules first). Both
numbers stand side by side; there is no single score. The list is a five-question-per-pack draft, so the false-accept
counts are a signal, not a rate.

## Threshold sweep (FAQ part alone, margin as chosen; the headline threshold was fixed before the run)

Counts of right answers (question / paraphrase / ASR variant, of 24 / 72 / 48 en, 24 / 72 / 53 ko) and false accepts
(of 15), embedding only. The full output for both configurations is in `docs/ledger/s2-1-sweep.txt`.

| Threshold | en: para / ASR / false accept | ko: para / ASR / false accept |
|---|---|---|
| 0.78 | 60 / 44 / 8 | 31 / 41 / 1 |
| 0.82 | 58 / 44 / 3 | 31 / 41 / 1 |
| 0.84 | 46 / 41 / 2 | 31 / 41 / 1 |
| 0.86 | 33 / 36 / 0 | 30 / 40 / 1 |
| 0.88 | 15 / 23 / 0 | 26 / 35 / 0 |
| 0.90 | 4 / 10 / 0 | 16 / 26 / 0 |

Reading: in English the model separates in-scope from out-of-scope reasonably, but a threshold that rejects every
out-of-scope question also rejects most paraphrases. In Korean the scores are compressed (many in-scope paraphrases score
below the level of one near-domain out-of-scope question), so no threshold gives both.

## Cost

Measured on the owner's CPU, 323 C00 queries, embeddings only (`python -m voxstage.retrieval bench e5-small`):
p50 31 ms, p95 46 ms per query; cold model load 21 s; index build for all six packs 1.5 s; resident memory about
1.2 GB (mostly `torch`); model on disk 493 MB. The S1 matcher is microseconds and needs no model.

## Findings

- Embeddings answer ASR-damaged questions much better than the rules (en 39/48 against 20/48; ko 39/53 against 26/53),
  because the rules need the exact words. Paraphrases are equal in English and worse in Korean when embeddings are used
  alone (25/72 against 36/72); in the FAQ part alone, 12 (en) and 19 (ko) cases the rules answered are lost, and 31 and
  21 cases are gained.
- Rules first loses nothing the rules had (0 cases) and adds the embedding gains: it has the higher pass rate of the two
  S2 configurations in both languages. It is not judged an improvement over S1 (see the verdict above), because it has
  false accepts where S1 has none.
- False accepts are near-domain questions: the loan interest rate question is answered with a nearby bank entry (en bank and
  ko bank), and one question each in shop and telecom (en) likewise. The rules had no false accept on this list. The list
  is five questions per pack and a draft, so these are counts to read as a signal, not as a rate.
- Korean with `multilingual-e5-small` and a zero-false-accept calibration is weak on paraphrases; a larger model
  (`bge-m3`) is the comparison the spec keeps for this.
- Embeddings only changes Korean C02 (a side question during a flow): an in-flow answer or side question is taken as an
  FAQ question more often. Not investigated further here.

## bge-m3 (separate row, run 2026-11-03)

Model `BAAI/bge-m3` from the official Hugging Face repository, **2293 MB downloaded** (2.3 GB; downloaded after the
owner's approval). Same code, same procedure: threshold and margin chosen on the same frozen calibration files before any
C00 run (commit `wip/S2-1b`): **en threshold 0.675, margin 0** (24/24 correct, 0/24 false accepts on the calibration set),
**ko threshold 0.69, margin 0** (23/24 correct, 0/24 false accepts). No prefixes (bge-m3 needs none). Nothing was changed
after seeing C00 numbers; the sweep below is descriptive.

C00 with the whole flow manager (clean = noisy for C00); S1 and e5 repeated from above:

| Configuration | en C00 | en question / paraphrase / ASR | en false accept | ko C00 | ko question / paraphrase / ASR | ko false accept |
|---|---|---|---|---|---|---|
| S1 rules | 89 / 144 | 24/24, 45/72, 20/48 | 0 / 15 | 86 / 149 | 24/24, 36/72, 26/53 | 0 / 15 |
| e5-small embedding only | 108 | 24/24, 45/72, 39/48 | 3 / 15 | 88 | 24/24, 25/72, 39/53 | 1 / 15 |
| e5-small rules first | 120 | 24/24, 55/72, 41/48 | 3 / 15 | 107 | 24/24, 42/72, 41/53 | 1 / 15 |
| bge-m3 embedding only | 123 | 24/24, 57/72, 42/48 | 2 / 15 | 109 | 24/24, 46/72, 39/53 | 1 / 15 |
| bge-m3 rules first | 126 | 24/24, 59/72, 43/48 | 2 / 15 | 113 | 24/24, 48/72, 41/53 | 1 / 15 |

Overall, all capabilities (clean / noisy): en 205 / 218 of 247 and ko 185 / 193 of 253 with rules first (S1: 168 / 181
and 158 / 166); embedding only: en 200 / 213, ko 180 / 188. The FAQ part alone (no flows around it): embedding only
134/144 (en) and 127/149 (ko); rules first 139/144 and 132/149 (S1 100 and 99; e5 117 / 94 and 133 / 121).

Against e5-small:

- **Korean paraphrases** improve a lot: 25/72 to 46/72 with embeddings only (e5 lost to the rules at 36/72; bge-m3 beats
  them), and 42/72 to 48/72 with rules first.
- **C02 (side question during a flow)**: Korean with embeddings only goes 4/6 (S1), 2/6 (e5), 3/6 (bge-m3); with rules
  first 4/6, no loss. English with embeddings only 5/6 to 4/6, and C13 3/8 against 4/8 (clean). Rules first changes nothing
  outside C00 in any language or mode. So the C02 drop is smaller with bge-m3, not gone.
- **False accepts** fall slightly (en 3 to 2, ko 1 to 1) but stay above S1's 0: the same near-domain questions
  (`shop.unanswerable.4`, `telecom.unanswerable.4` in English, `telecom.unanswerable.4` in Korean).

**Verdict by the S2-7 criterion: not judged an improvement over S1**, for the same reason as e5: false accepts 2/15 (en)
and 1/15 (ko) against 0/15. The pass rate is the highest of the rows.

Cost (the same `bench`, 323 queries): p50 273 ms, p95 356 ms per query (e5-small 31 / 46 ms); cold load 34 s; index build
for all six packs 7 s; resident memory about 2.0 GB; 2293 MB on disk. About nine times slower per query than e5-small.

Sweep (embedding only, `docs/ledger/s2-1-sweep-bge-m3.txt`): the scores sit lower than e5's, so the default grid was run
again with lower values. At the chosen thresholds the sweep matches the evaluation. In Korean a threshold of 0.70 would give
0 false accepts with 59/72 paraphrases and 42/53 ASR variants; in English the two false accepts remain down to 0.70 and
disappear only at 0.75, where paraphrases fall to 47/72. This is an observation about the draft list, not a new threshold:
the headline threshold stays the one chosen on the calibration set.

## S2-1c: conservative thresholds, false accepts back to S1's level (run 2026-11-04)

Goal set by the owner: bring false accepts down to S1's 0. Branch `wip/S2-1c`; no extra download.

**What changed, and what did not.** The S2-1 selection rule already was "zero false accepts on the calibration set first,
then the most correct answers", so running it again would return the same values. What was wrong is that those thresholds
sit on the highest out-of-scope calibration score (e5-small en 0.835 against 0.834; bge-m3 en 0.675 against 0.673), with no
room for a question that scores a little higher. The new rule (`safety_floor`, `calibrate --safe`) keeps the objective and
adds a floor, computed from the calibration scores only: **threshold >= max + (max - median)** of the out-of-scope top-1
scores. The rule was fixed before any C00 run; the calibration files, the frozen S2-1 values (`models`) and every S1 number
are untouched. The new values are in `safe_models` of `domains/retrieval.yaml` (same calibration hashes).

| Model | Language | Threshold (was) | Margin | Floor | Correct / false accepts on calibration |
|---|---|---|---|---|---|
| e5-small | en | 0.87 (0.835) | 0 | 0.8683 | 6 / 24, 0 / 24 |
| e5-small | ko | 0.995 (0.86) | 0 | 0.9328 | 0 / 24, 0 / 24 |
| bge-m3 | en | 0.81 (0.675) | 0 | 0.8051 | 12 / 24, 0 / 24 |
| bge-m3 | ko | 0.82 (0.69) | 0 | 0.8188 | 12 / 24, 0 / 24 |

The e5-small Korean floor lies above every in-scope calibration score, so the rule leaves nothing: the threshold ends at
the top of the grid and e5-small Korean answers nothing by embedding. This is the rule's result, not a tuned one; it is
reported as it is.

### C00 with the whole flow manager (clean = noisy for C00); false accepts on the draft list

| Configuration | en C00 | en question / paraphrase / ASR | en FA | ko C00 | ko question / paraphrase / ASR | ko FA |
|---|---|---|---|---|---|---|
| S1 rules | 89 / 144 | 24/24, 45/72, 20/48 | 0 / 15 | 86 / 149 | 24/24, 36/72, 26/53 | 0 / 15 |
| e5-small rules first (S2-1, plain) | 120 | 24/24, 55/72, 41/48 | 3 | 107 | 24/24, 42/72, 41/53 | 1 |
| bge-m3 rules first (S2-1b, plain) | 126 | 24/24, 59/72, 43/48 | 2 | 113 | 24/24, 48/72, 41/53 | 1 |
| **e5-small rules first, safe** | 108 | 24/24, 50/72, 34/48 | **0** | 86 | 24/24, 36/72, 26/53 | **0** |
| e5-small embedding only, safe | 76 | 24/24, 21/72, 31/48 | 0 | 0 | 0/24, 0/72, 0/53 | 0 |
| **bge-m3 rules first, safe** | 101 | 24/24, 48/72, 29/48 | **0** | 95 | 24/24, 38/72, 33/53 | **0** |
| bge-m3 embedding only, safe | 65 | 24/24, 23/72, 18/48 | 0 | 68 | 24/24, 16/72, 28/53 | 0 |

Other capabilities: C02 (side question in a flow) is 5/6 en and 4/6 ko with rules first for both models, no loss against
S1; with embeddings only it drops (e5 en 3/6, ko 0/6; bge-m3 en 3/6, ko 1/6). Overall, all capabilities, clean · noisy:
e5 rules first en 187 · 200 of 247, ko 158 · 166 of 253 (S1: 168 · 181, 158 · 166); bge-m3 rules first en 180 · 193, ko
167 · 175. The embedding-only rows were run clean only for the cost of time; their C00 is the same in noisy mode.

### Verdict by the S2-7 criterion

False accepts are **0 / 15 in both languages for every safe configuration, equal to S1**, so none of them is worse on
false accepts, and the rules-first ones raise the pass rate:

- **bge-m3 rules first, safe: counted as an improvement over S1** (C00 en 89 to 101, ko 86 to 95; Korean paraphrases
  36 to 38 of 72, ASR variants 26 to 33 of 53; C02 no loss). It is the **candidate for a default**: the only configuration
  that gains in both languages with zero false accepts. Cost is the heavy one: 2293 MB model, p50 273 ms per embedding
  query (only for utterances the rules did not answer), about 2.0 GB resident.
- **e5-small rules first, safe: improvement in English only** (89 to 108); Korean equals S1 exactly because the embedding
  step never fires. The cheap option (493 MB, p50 31 ms, about 1.2 GB) if Korean is not needed from embeddings.
- Embedding-only safe rows lose to S1 on C00 (en 65 and 76 against 89) and on C02; they are not candidates.

The default has **not** been changed; that is the owner's decision.

### Limits (read before trusting the zero)

- The calibration set is 24 out-of-scope questions per language, mostly far from the domain (weather, jokes); the
  near-domain questions that were false accepts in S2-1 are rare in it. A threshold with zero false accepts on 24 items
  can be a result of that set being easy, not of the threshold being safe. The floor adds room but is a heuristic.
- The zero on the test side is counted on the five-questions-per-pack draft list (15 per language, "draft, not reviewed by
  the owner"). It is a signal, not a rate; a larger and reviewed out-of-scope list would be the real test.
- The price of the zeros is the pass rate: against plain S2-1 rules first, C00 falls (bge-m3 126 to 101 en, 113 to 95 ko;
  e5-small 120 to 108 en, 107 to 86 ko). The two thresholds draw one line between "accept more" and "accept fewer"; this
  run moved to the cautious end because the owner asked for it.
- Latency and memory are those of the models above (same code, same models); not measured again.

## Not done

- Score fusion (not built, by decision S2-4) and extra indexed example questions (not in S2-1, decision S2-5).
