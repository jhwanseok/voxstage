"""FAQ retrieval with sentence embeddings (S2-1, decisions S2-3 to S2-7).

The same job as `rules/faq.py`, done by similarity search: the canonical question of every FAQ entry is embedded when
the domain pack is first used, and an utterance is answered by the entry whose question is most similar, if the
similarity passes a threshold (and leads the runner-up by a margin). Otherwise it is a miss, handled by the S1 fallback
(miss counter, hand-off).

    python -m voxstage.retrieval download e5-small      # the only command that touches the network
    python -m voxstage.retrieval calibrate e5-small     # choose threshold and margin on faq_calibration.yaml
    python -m voxstage.retrieval sweep e5-small en      # accuracy and false accepts at many thresholds
    python -m voxstage.retrieval bench e5-small         # latency and memory

Evaluate it like any manager: `python -m voxstage.evaluate run voxstage.retrieval:embed_e5 --lang en`
(`embed_*`: embeddings only; `hybrid_*`: the keyword rules first, embeddings when no rule matches). `flow_embed_*` and
`flow_hybrid_*` are the same with the whole S1 flow manager around them, for the stage table. The `*_safe` versions
(S2-1c) use the thresholds chosen with a safety floor (`calibrate <model> --safe`, section `safe_models`).

Held-out: only `dataset.authoring_view` (id, question, answer) is read for indexing. The held-out fields of the FAQ file
are not read here (a test checks this); threshold and margin come only from `faq_calibration.yaml`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Optional

import yaml

from . import dataset
from .domain_pack import Pattern
from .rules.faq import FaqRuleManager, _pack

DOMAINS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "domains")
CONFIG_PATH = os.path.join(DOMAINS_DIR, "retrieval.yaml")


@dataclass(frozen=True)
class Model:
    key: str
    name: str            # the Hugging Face repository
    query_prefix: str    # e5 expects "query: " on the question and "passage: " on the indexed text
    passage_prefix: str


MODELS = {
    "e5-small": Model("e5-small", "intfloat/multilingual-e5-small", "query: ", "passage: "),
    "bge-m3": Model("bge-m3", "BAAI/bge-m3", "", ""),
}


class ModelMissing(RuntimeError):
    """The model is not in the local cache. Run `python -m voxstage.retrieval download <model>`."""


class SentenceEmbedder:
    """Loads a sentence-transformers model lazily from the local cache; never downloads by itself."""

    def __init__(self, model: Model):
        self.model = model
        self._st = None

    def _load(self):
        if self._st is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ModelMissing("sentence-transformers is not installed (pip install -e .[retrieval])") from exc
            try:
                self._st = SentenceTransformer(self.model.name, local_files_only=True)
            except Exception as exc:   # an offline cache miss is an OSError subclass in several versions
                raise ModelMissing(f"{self.model.name} is not in the local cache: {exc}") from exc
        return self._st

    def encode_queries(self, texts: list):
        return self._encode([self.model.query_prefix + t for t in texts])

    def encode_passages(self, texts: list):
        return self._encode([self.model.passage_prefix + t for t in texts])

    def _encode(self, texts: list):
        return self._load().encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)


def available(model_key: str) -> bool:
    """Is the model usable on this machine (package and cached weights)?"""
    try:
        SentenceEmbedder(MODELS[model_key])._load()
        return True
    except ModelMissing:
        return False


class EmbeddingMatcher:
    """`match(text) -> (Pattern | None, trace)`, the signature of the rule matcher."""

    def __init__(self, entries: list, embedder, threshold: float, margin: float = 0.0):
        import numpy as np
        self.ids = [e[0] for e in entries]
        self.embedder, self.threshold, self.margin = embedder, threshold, margin
        self.matrix = np.asarray(embedder.encode_passages([e[1] for e in entries]))

    def scores(self, text: str):
        """(best id, best similarity, second similarity)."""
        import numpy as np
        sims = self.matrix @ np.asarray(self.embedder.encode_queries([text])[0])
        order = np.argsort(-sims)
        second = float(sims[order[1]]) if len(order) > 1 else -1.0
        return self.ids[int(order[0])], float(sims[order[0]]), second

    def match(self, text: str) -> tuple:
        best, s1, s2 = self.scores(text)
        trace = {"matched": None, "retrieval": {"best": best, "score": round(s1, 4), "second": round(s2, 4)}}
        if s1 < self.threshold:
            trace["retrieval"]["rejected"] = "below_threshold"
            return None, trace
        if s1 - s2 < self.margin:
            trace["retrieval"]["rejected"] = "below_margin"
            return None, trace
        trace["matched"] = best
        return Pattern(best, (), (), ()), trace


class HybridMatcher:
    """The keyword rules first; the embeddings only when no rule matches."""

    def __init__(self, rules, embeddings: EmbeddingMatcher):
        self.rules, self.embeddings = rules, embeddings

    def match(self, text: str) -> tuple:
        pattern, trace = self.rules.match(text)
        if pattern is not None:
            return pattern, {**trace, "by": "rules"}
        pattern, trace2 = self.embeddings.match(text)
        return pattern, {**trace, **trace2, "by": "embeddings" if pattern else "none"}


class FaqEmbeddingManager(FaqRuleManager):
    """`FaqRuleManager` with another matcher: answers, miss counter and hand-off stay the S1 ones."""

    def __init__(self, pack, matcher, name: str):
        super().__init__(pack)
        self.rule_matcher = self.matcher
        self.matcher = matcher
        self.name = name


def load_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        raise ModelMissing(f"{path} does not exist: run `python -m voxstage.retrieval calibrate <model> --write`")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_EMBEDDERS: dict = {}
_MATCHERS: dict = {}


def embedder(model_key: str) -> SentenceEmbedder:
    if model_key not in _EMBEDDERS:
        _EMBEDDERS[model_key] = SentenceEmbedder(MODELS[model_key])
    return _EMBEDDERS[model_key]


def embedding_matcher(domains_dir: str, domain: str, lang: str, model_key: str,
                      threshold: Optional[float] = None, margin: Optional[float] = None,
                      profile: str = "plain") -> EmbeddingMatcher:
    if threshold is None or margin is None:
        chosen = load_config()["safe_models" if profile == "safe" else "models"][model_key][lang]
        threshold = chosen["threshold"] if threshold is None else threshold
        margin = chosen["margin"] if margin is None else margin
    key = (domains_dir, domain, lang, model_key, threshold, margin)
    if key not in _MATCHERS:
        entries = [(i, q) for i, q, _ in dataset.authoring_view(os.path.join(domains_dir, domain), lang)]
        _MATCHERS[key] = EmbeddingMatcher(entries, embedder(model_key), threshold, margin)
    return _MATCHERS[key]


def build_manager(domains_dir: str, domain: str, lang: str, model_key: str, mode: str,
                  threshold: Optional[float] = None, margin: Optional[float] = None,
                  profile: str = "plain") -> FaqEmbeddingManager:
    """mode: `embed` (embeddings only) or `hybrid` (rules first). profile: `plain` (S2-1) or `safe` (S2-1c)."""
    pack = _pack(domains_dir, domain, lang)
    emb = embedding_matcher(domains_dir, domain, lang, model_key, threshold, margin, profile)
    manager = FaqEmbeddingManager(pack, emb, f"faq_{mode}_{model_key}" + ("_safe" if profile == "safe" else ""))
    if mode == "hybrid":
        manager.matcher = HybridMatcher(manager.rule_matcher, emb)
    return manager


def _factory(model_key: str, mode: str, profile: str = "plain"):
    def factory(ctx):
        from .evaluate import DEFAULT_DOMAINS_DIR
        return build_manager(DEFAULT_DOMAINS_DIR, ctx.domain, ctx.lang, model_key, mode, profile=profile)
    factory.__name__ = f"{mode}_{model_key.replace('-', '_')}" + ("_safe" if profile == "safe" else "")
    return factory


def _flow_factory(model_key: str, mode: str, profile: str = "plain"):
    """The whole S1 flow manager (flows, side questions, gate) with the FAQ part replaced: the S2 row of the stage table."""
    def factory(ctx):
        from .evaluate import DEFAULT_DOMAINS_DIR
        from .rules.interpreter import build_manager as flow_manager
        manager = flow_manager(DEFAULT_DOMAINS_DIR, ctx.domain, ctx.lang, ctx.tools)
        manager.faq = build_manager(DEFAULT_DOMAINS_DIR, ctx.domain, ctx.lang, model_key, mode, profile=profile)
        return manager
    factory.__name__ = f"flow_{mode}_{model_key.replace('-', '_')}" + ("_safe" if profile == "safe" else "")
    return factory


embed_e5 = _factory("e5-small", "embed")
hybrid_e5 = _factory("e5-small", "hybrid")
embed_bge = _factory("bge-m3", "embed")
hybrid_bge = _factory("bge-m3", "hybrid")
flow_embed_e5 = _flow_factory("e5-small", "embed")
flow_hybrid_e5 = _flow_factory("e5-small", "hybrid")
flow_embed_bge = _flow_factory("bge-m3", "embed")
flow_hybrid_bge = _flow_factory("bge-m3", "hybrid")
embed_e5_safe = _factory("e5-small", "embed", "safe")
hybrid_e5_safe = _factory("e5-small", "hybrid", "safe")
embed_bge_safe = _factory("bge-m3", "embed", "safe")
hybrid_bge_safe = _factory("bge-m3", "hybrid", "safe")
flow_embed_e5_safe = _flow_factory("e5-small", "embed", "safe")
flow_hybrid_e5_safe = _flow_factory("e5-small", "hybrid", "safe")
flow_embed_bge_safe = _flow_factory("bge-m3", "embed", "safe")
flow_hybrid_bge_safe = _flow_factory("bge-m3", "hybrid", "safe")


# --- calibration (S2-6): the only place a threshold or margin is chosen -----------------------------------
def load_calibration(path: str) -> tuple:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or set(raw) != {"status", "lang", "in_scope", "out_of_scope"}:
        raise ValueError(f"{path}: needs status, lang, in_scope and out_of_scope")
    return [(x["id"], x["text"]) for x in raw["in_scope"]], list(raw["out_of_scope"])


def calibration_hash(domains_dir: str, lang: str) -> str:
    h = hashlib.sha256()
    for d in dataset.DOMAINS:
        with open(os.path.join(domains_dir, d, lang, "faq_calibration.yaml"), "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))   # the same hash with LF or CRLF line ends
    return h.hexdigest()[:16]


THRESHOLDS = [round(0.50 + 0.005 * i, 3) for i in range(100)]   # 0.50 .. 0.995
MARGINS = [0.0, 0.01, 0.02, 0.03, 0.05]


def safety_floor(scored_out: list) -> float:
    """S2-1c: the threshold may not sit on the highest out-of-scope score. It must clear it by the distance the tail of
    the out-of-scope scores reaches above their median: floor = max + (max - median), from calibration scores only."""
    scores = sorted(s[1] for s in scored_out)
    top, median = scores[-1], scores[len(scores) // 2] if len(scores) % 2 else (scores[len(scores) // 2 - 1] + scores[len(scores) // 2]) / 2
    return top + (top - median)


def choose(scored_in: list, scored_out: list, safe: bool = False) -> dict:
    """scored_*: lists of (best id, s1, s2[, expected id]). Zero false accepts first, then most correct answers;
    ties go to the larger threshold, then the smaller margin. `safe` (S2-1c) also keeps the threshold at or above
    `safety_floor`, so that zero false accepts on the calibration set is not reached by hugging its highest score."""
    best = None
    floor = safety_floor(scored_out) if safe and scored_out else 0.0
    for t in THRESHOLDS:
        if t < floor:
            continue
        for m in MARGINS:
            def ok(s):
                return s[1] >= t and s[1] - s[2] >= m
            fa = sum(ok(s) for s in scored_out)
            correct = sum(ok(s) and s[0] == s[3] for s in scored_in)
            key = (-fa, correct, t, -m)
            if best is None or key > best[0]:
                best = (key, {"threshold": t, "margin": m, "false_accepts": fa, "out_of_scope": len(scored_out),
                              "correct": correct, "in_scope": len(scored_in)})
    if safe:
        best[1]["floor"] = round(floor, 4)
    return best[1]


def calibrate(model_key: str, domains_dir: str = DOMAINS_DIR, safe: bool = False) -> dict:
    out = {}
    for lang in dataset.LANGS:
        scored_in, scored_out = [], []
        for d in dataset.DOMAINS:
            matcher = embedding_matcher(domains_dir, d, lang, model_key, threshold=0.0, margin=0.0)
            ins, outs = load_calibration(os.path.join(domains_dir, d, lang, "faq_calibration.yaml"))
            scored_in += [(*matcher.scores(t), i) for i, t in ins]
            scored_out += [matcher.scores(t) for t in outs]
        out[lang] = {**choose(scored_in, scored_out, safe), "calibration_hash": calibration_hash(domains_dir, lang)}
    return out


# --- sweep and bench ---------------------------------------------------------------------------------------
def _c00_queries(domains_dir: str, lang: str) -> list:
    from .evaluate import build_cases
    rows = []
    for c in build_cases(domains_dir, lang, include_unanswerable=True):
        if c.capability != "C00" or c.kind not in ("faq", "unanswerable"):
            continue
        expected = c.id.split("#")[0] if c.kind == "faq" else None
        rows.append((c.domain, c.source, c.turns[0].user["text"], expected))
    return rows


def sweep(model_key: str, lang: str, mode: str = "embed", domains_dir: str = DOMAINS_DIR, thresholds=None) -> list:
    """Rows of {threshold, accuracy by source, false accepts}, computed from one pass of scores. For `hybrid` the
    rule result is fixed and only the embedding fallback changes."""
    margin = load_config()["models"][model_key][lang]["margin"]
    rows = []
    for domain, source, text, expected in _c00_queries(domains_dir, lang):
        matcher = embedding_matcher(domains_dir, domain, lang, model_key, threshold=0.0, margin=0.0)
        rule = None
        if mode == "hybrid":
            rule, _ = _pack_rules(domains_dir, domain, lang).match(text)
        rows.append((source, expected, matcher.scores(text), rule.id if rule else None))
    out = []
    for t in thresholds or [0.70, 0.75, 0.78, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92]:
        counts: dict = {}
        for source, expected, (best, s1, s2), rule_id in rows:
            answered = rule_id if rule_id else (best if s1 >= t and s1 - s2 >= margin else None)
            c = counts.setdefault(source, [0, 0])
            c[1] += 1
            c[0] += (answered == expected) if expected else (answered is not None)   # unanswerable: count false accepts
        out.append({"threshold": t, **{k: f"{v[0]}/{v[1]}" for k, v in sorted(counts.items())}})
    return out


def _pack_rules(domains_dir: str, domain: str, lang: str):
    return FaqRuleManager(_pack(domains_dir, domain, lang)).matcher


def bench(model_key: str, domains_dir: str = DOMAINS_DIR) -> dict:
    t0 = time.perf_counter()
    emb = embedder(model_key)
    emb.encode_queries(["warm up"])
    load_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    for d in dataset.DOMAINS:
        for lang in dataset.LANGS:
            embedding_matcher(domains_dir, d, lang, model_key, threshold=0.5, margin=0.0)
    index_s = time.perf_counter() - t0
    times = []
    for lang in dataset.LANGS:
        for domain, _, text, _ in _c00_queries(domains_dir, lang):
            m = embedding_matcher(domains_dir, domain, lang, model_key, threshold=0.5, margin=0.0)
            t0 = time.perf_counter()
            m.match(text)
            times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    result = {"model": model_key, "queries": len(times), "cold_load_s": round(load_s, 2),
              "index_build_s_all_packs": round(index_s, 2), "p50_ms": round(statistics.median(times), 1),
              "p95_ms": round(times[int(0.95 * (len(times) - 1))], 1)}
    try:
        import psutil
        result["rss_mb"] = round(psutil.Process().memory_info().rss / 1e6)
    except ImportError:
        result["rss_mb"] = None
    return result


def download(model_key: str) -> dict:
    """The one command that uses the network. Reports the size of the downloaded files."""
    from sentence_transformers import SentenceTransformer
    model = MODELS[model_key]
    st = SentenceTransformer(model.name)
    path = st[0].auto_model.config._name_or_path if hasattr(st[0], "auto_model") else ""
    from huggingface_hub import snapshot_download
    folder = snapshot_download(model.name, local_files_only=True)
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(os.path.realpath(folder)) for f in fs)
    return {"model": model.name, "folder": folder, "size_mb": round(size / 1e6), "loaded_from": path}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m voxstage.retrieval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("download", "calibrate", "bench"):
        p = sub.add_parser(name)
        p.add_argument("model", choices=sorted(MODELS))
        if name == "calibrate":
            p.add_argument("--write", action="store_true", help="write the chosen values to domains/retrieval.yaml")
            p.add_argument("--safe", action="store_true", help="S2-1c: keep the threshold above the safety floor")
    s = sub.add_parser("sweep")
    s.add_argument("model", choices=sorted(MODELS))
    s.add_argument("lang", choices=dataset.LANGS)
    s.add_argument("--mode", default="embed", choices=("embed", "hybrid"))
    args = ap.parse_args(argv)
    if args.cmd == "download":
        print(json.dumps(download(args.model), indent=1))
    elif args.cmd == "calibrate":
        chosen = calibrate(args.model, safe=args.safe)
        print(json.dumps(chosen, indent=1))
        if args.write:
            config = load_config() if os.path.exists(CONFIG_PATH) else {}
            config.setdefault("safe_models" if args.safe else "models", {})[args.model] = chosen
            with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
                f.write("# Threshold and margin per model and language, chosen on faq_calibration.yaml only (S2-6).\n")
                yaml.safe_dump(config, f, sort_keys=True, allow_unicode=True)
    elif args.cmd == "sweep":
        for row in sweep(args.model, args.lang, args.mode):
            print(json.dumps(row))
    else:
        print(json.dumps(bench(args.model), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
