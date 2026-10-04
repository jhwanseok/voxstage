# voxstage — a staged voicebot engine, observable from the first line

From rule-based to LLM to agent, batch to streaming: one repo, one swappable stage at a time.
License: Apache-2.0. Project principles: [docs/project-principles.md](docs/project-principles.md).

Every stage of the pipeline (endpointing, ASR, LLM, sentence chunking, TTS, playback)
emits structured events to a JSONL log. Latency, cost and errors are *derived from that
log*, so a number is always traceable to the events that produced it.

**Status: v0.0.1.** The measurement stack is tested with mock vendors. The real adapters
(faster-whisper, MeloTTS, Gemini) are written but have **not yet been run** — first
real run happens on Colab (see `notebooks/colab_quickstart.ipynb`).

## What is measured

| segment | meaning | how |
|---|---|---|
| T1 | speech end → endpoint detected | audio time vs. ground-truth end of speech |
| T2 | endpoint → ASR final | `time.monotonic()` |
| T3 | LLM request → first token | `time.monotonic()` |
| T3b | first token → first speakable sentence | added: this is the cost of sentence chunking |
| T4 | TTS request → first audio chunk | `time.monotonic()` |
| T5 | first chunk → playback start | **n/a** with the null sink (headless/Colab) |
| E2E | speech end → first audio chunk | T1 + wall time after the endpoint |

Reports give n, mean, p50, p95, p99, max per segment, a histogram PNG, and shadow cost.
Warm-up and failed turns are excluded and counted.

## Quickstart (no GPU, no API key, no cost)

```bash
pip install numpy matplotlib
python -m unittest discover -s tests -v
python -m voxstage.make_audio --tts mock --out data/audio
python -m voxstage.bench --audio-dir data/audio --out runs/mock --repeats 8
```

`runs/mock/` then holds `events.jsonl`, `meta.json`, `report.md`, `summary.json`, `latency_hist.png`.
(Mock sleeps are real by default. Add `--asr-opt time_scale=0.05` etc. for a fast smoke run.)

## Real run on Colab (free tier)

See the notebook. Short version: faster-whisper (ASR) + MeloTTS Korean (TTS) on the T4,
Gemini free tier for the LLM, key from the Colab Secrets panel.

```bash
python -m voxstage.make_audio --tts melo --out data/audio
python -m voxstage.bench --asr whisper --asr-opt model=large-v3-turbo --asr-opt device=cuda \
  --llm gemini --llm-opt model=<pinned-model-name> --llm-opt thinking=off \
  --tts melo --tts-opt device=cuda --rpm 8 --repeats 20 --warmup 3
```

## Known limits (read before quoting any number)

- **Colab hardware is shared and noisy.** Absolute numbers are indicative; run-to-run
  comparisons are only fair inside one session or with many repeats. `meta.json` records
  the GPU and package versions.
- **Whisper is not a streaming ASR.** T2 is "endpoint → full-utterance transcript".
- **MeloTTS is not a streaming TTS.** T4 is sentence-level synthesis time, not first-packet time.
- **No real playback on Colab.** T5 is reported as n/a rather than faked.
- **Test audio is TTS-generated and clean**, so ASR is optimistic. Noisy / real-mic audio is a later step.
- **Gemini free tier:** rate limits and model availability change; pin one model per run.
  Inputs/outputs on the free tier may be used by Google to improve its products, so only
  synthetic test text goes through it. Thinking is turned off by default because thinking
  tokens add latency (if the model rejects that, the adapter retries once and records it).
- **Stages run sequentially (v0).** First-sentence timings are exact; later sentences do not
  model LLM/TTS overlap. Pipelining is the first planned engine change, and this benchmark
  is its baseline.
- n < 100 per segment makes p99 essentially the max; the report says so.

## Layout

```
voxstage/events.py        JSONL event log
voxstage/interfaces.py    ASR / LLM / TTS / Sink contracts
voxstage/endpointer.py    energy endpointer (audio-time T1)
voxstage/pipeline.py      one-turn pipeline + sentence chunker
voxstage/metrics.py       events -> p50/p95/p99, markdown, histograms
voxstage/cost.py          shadow cost from a price table you fill in
voxstage/bench.py         runner (warm-up, interleaving, throttling, meta)
voxstage/make_audio.py    ground-truth test audio generator
voxstage/vendors/         mock, faster-whisper, MeloTTS, Gemini
```
