# Dataset spec

Datasets are data only. The rule behind it: the core never imports domain code, so adding a
domain must leave `git diff --stat voxstage/` empty. Decision record:
[0005](decisions/0005-dataset-first-development.md). Everything here is synthetic and written
from scratch.

## Layout

```
domains/<domain>/          domain = bank | shop | telecom
  tools.yaml               fake backend API (rules keyed by arguments, ADR 0004); shared by all languages
  <lang>/                  en first; ko is added later as a parallel directory (ADR 0006)
    faq.yaml               C00: FAQ entries with paraphrase and recognition-error variants
    scenarios/*.yaml       one capability case per file
```

Every `faq.yaml` and scenario file carries `lang:`, which must match its directory. Ids are
shared across languages (`bank.C05.001` is the same case in `en` and `ko`), so a translated
case keeps its id.

Check the files and see progress with `python -m voxstage.dataset coverage [domains_dir] [lang]`. Loading is strict:
unknown keys, wrong capability ids, unquoted digits and mismatched directories all fail at
load time with the file name.

## Capabilities

| Id | Capability | Notes |
|---|---|---|
| C00 | FAQ answer (baseline) | start point: STT, FAQ, TTS |
| C01 | Scenario switch | condition-based move between flows |
| C02 | Return after a side question | digression, then resume |
| C03 | Cancel, back, hand off to an agent | |
| C04 | Button / DTMF input | non-speech input, no recognition error |
| C05 | Slot re-fill after misrecognition | confirm, re-ask, correct |
| C06 | Multiple slots, omissions, references | |
| C07 | Number, date, time normalisation | |
| C08 | Answer from attributes and API results | |
| C09 | Condition-specific fixed answer | verbatim wording, and when it must not appear |
| C10 | External API failure or delay fallback | |
| C11 | Block information before identity check | |
| C12 | Policy-change impact | measured by regressions after a change |

## FAQ entry

```yaml
lang: en
entries:
  - id: bank.faq.hours
    question: canonical question
    answer: the verbatim reply
    paraphrases: [at least three other ways to ask]
    asr_variants: [at least one hand-written recognition error]
```

`asr_variants` are plausible errors written by hand (spacing, similar sounds), not real ASR
output. They stand in for noise until audio mode exists.

## Scenario

```yaml
id: bank.C05.001               # <domain>.<capability>.<number>, must match the directory and fields
lang: en                       # must match the <lang>/ directory
domain: bank
capability: C05
title: "quote titles that contain a colon"
tags: [dst, correction]
setup:                         # optional fixtures, e.g. customer attributes
  customer: {grade: gold}
turns:
  - user:                      # exactly one of three input kinds
      kind: utterance          # text (+ optional asr_text: what the recognizer "heard")
      text: Transfer thirty dollars please
      asr_text: Transfer thirteen dollars please
    expect:                    # all keys optional
      flow: transfer
      slots: {amount: "100000"}
      reply_contains: [...]          # each string must appear exactly (verbatim checks)
      reply_contains_any: [...]      # at least one must appear
      reply_not_contains: [...]      # none may appear
      tool_calls: [{name: get_x, args: {k: "v"}}]
      actions: [HandOff]
  - user: {kind: dtmf, digits: "4821"}        # quote digits so YAML keeps them as text
  - user: {kind: button, button_id: menu_balance}
variants:                      # optional: other wordings for one utterance turn
  - turn: 1
    texts: [...]
```

Expectations check the end state (flow, slots, tool calls, required and forbidden phrases),
not exact wording, except where wording is the requirement (C09).

## Authoring rules

1. Write cases for generic bank, shop and telecom situations. Do not transcribe or adapt any
   employer scenario, flow or terminology.
2. Every capability case should be one a competent rule-based system could pass; a case that
   only an LLM could pass belongs under a capability that says so in its notes.
3. Keep digits and numbers in quotes.
4. Reviewed and approved by the repo owner before a capability is implemented against it.

## Status

Pilot slice (bank, English): C00 plus C01, C04, C05, C08, C09, reviewed and approved. The
remaining capabilities and the shop and telecom domains follow. Korean comes later, as a
parallel `ko/` directory with the same ids.
