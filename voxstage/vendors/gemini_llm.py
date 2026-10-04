"""Gemini streaming adapter (google-genai SDK).

Free-tier notes that affect measurement:
- Rate limits are per model and per project and change over time; keep requests
  throttled (the bench runner does this outside timed regions) and read 429s as data.
- Thinking tokens add latency. We turn thinking off by default; if the chosen
  model rejects that setting we retry once without it and record the fallback.
- Free-tier prompts/outputs may be used by Google to improve its products. Only
  send synthetic test text through this adapter.

The model name is deliberately a required, explicit setting: available free-tier
models change, so pin one per run and record it in meta.json.
"""

from __future__ import annotations

import os

from ..interfaces import LLM


class GeminiLLM(LLM):
    def __init__(self, model: str | None = None, api_key: str | None = None,
                 max_output_tokens: int = 120, temperature: float = 0.3,
                 thinking: str = "off", **_):
        from google import genai  # imported lazily: optional dependency

        model = model or os.environ.get("GEMINI_MODEL")
        if not model:
            raise ValueError("Set llm-opt model=<name> or GEMINI_MODEL. Pin one model per run.")
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError("Set GEMINI_API_KEY (Colab: Secrets panel).")
        self.name = f"gemini:{model}"
        self._model = model
        self._client = genai.Client(api_key=key)
        self._max = int(max_output_tokens)
        self._temp = float(temperature)
        self._thinking = thinking
        self.last_usage = {}

    def _config(self, system: str, with_thinking: bool):
        from google.genai import types

        kwargs = dict(system_instruction=system, max_output_tokens=self._max, temperature=self._temp)
        if with_thinking and self._thinking == "off":
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**kwargs)

    def stream(self, messages):
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages if m["role"] != "system"
        ]
        self.last_usage = {"thinking_fallback": 0}
        try:
            yield from self._run(contents, self._config(system, True))
        except Exception as exc:
            if "thinking" in str(exc).lower() and self._thinking == "off":
                self.last_usage["thinking_fallback"] = 1
                yield from self._run(contents, self._config(system, False))
            else:
                raise

    def _run(self, contents, config):
        last = None
        for chunk in self._client.models.generate_content_stream(
                model=self._model, contents=contents, config=config):
            last = chunk
            if chunk.text:
                yield chunk.text
        meta = getattr(last, "usage_metadata", None)
        if meta is not None:
            self.last_usage.update({
                "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
            })
