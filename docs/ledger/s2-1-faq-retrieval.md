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
- Rules first loses nothing the rules had (0 cases) and adds the embedding gains: it is the better configuration on pass
  rate in both languages.
- False accepts are near-domain questions: the loan interest rate question is answered with a nearby bank entry (en bank and
  ko bank), and one question each in shop and telecom (en) likewise. The rules had no false accept on this list. The list
  is five questions per pack and a draft, so these are counts to read as a signal, not as a rate.
- Korean with `multilingual-e5-small` and a zero-false-accept calibration is weak on paraphrases; a larger model
  (`bge-m3`) is the comparison the spec keeps for this.
- Embeddings only changes Korean C02 (a side question during a flow): an in-flow answer or side question is taken as an
  FAQ question more often. Not investigated further here.

## Not done

- `bge-m3` was not downloaded or run. Its size is about 2.3 GB, over the 1 GB limit the owner's instruction set for
  downloading without asking, so it waits for a go-ahead.
- Score fusion (not built, by decision S2-4) and extra indexed example questions (not in S2-1, decision S2-5).
