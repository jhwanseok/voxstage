"""FAQ by keyword rules: question in, verbatim answer out (R1, ADR 0009).

Per entry: `all_of` (every group needs one of its words), `any_of` (at least one, if given), `none_of` (none),
`priority`, and `regex` as an alternative path for what a word group cannot say. The best match is the highest
priority, then the most specific (more matched words), then file order. No match is a miss; after
`max_misses` consecutive misses the manager hands off or ends the call, as configured.
"""

from __future__ import annotations

import re
from typing import Optional

from ..dialogue import DialogueManager, DMResult, EndCall, HandOff
from ..domain_pack import DomainPack, Pattern
from ..turn import Utterance
from .tokenize import Tokenizer, for_lang

MISSES = "faq_misses"


class FaqRuleManager(DialogueManager):
    name = "faq_rules"

    def __init__(self, pack: DomainPack, tokenizer: Optional[Tokenizer] = None):
        if pack.fallback is None:
            raise ValueError(f"{pack.domain}/{pack.lang}: no rules/config.yaml (fallback policy) in the pack")
        self.pack = pack
        self.tok = tokenizer or for_lang(pack.lang)
        self._regex = {p.id: tuple(re.compile(r, re.IGNORECASE) for r in p.regex) for p in pack.patterns}

    def _score(self, p: Pattern, text: str, analysis) -> Optional[int]:
        """Number of matched words if the pattern matches, else None."""
        if any(self.tok.has(analysis, w) for w in p.none_of):
            return None
        hits, ok = 0, True
        for group in p.all_of:
            if any(self.tok.has(analysis, w) for w in group):
                hits += 1
            else:
                ok = False
                break
        if ok and p.any_of:
            n = sum(self.tok.has(analysis, w) for w in p.any_of)
            if n == 0:
                ok = False
            hits += n
        if ok and (p.all_of or p.any_of):
            return hits
        if any(r.search(text) for r in self._regex[p.id]):
            return max(hits, 1)
        return None

    def match(self, text: str) -> tuple:
        """(pattern or None, trace)"""
        analysis = self.tok.analyze(text)
        scored = []
        for order, p in enumerate(self.pack.patterns):
            s = self._score(p, text, analysis)
            if s is not None:
                scored.append((p.priority, s, -order, p))
        if not scored:
            return None, {"tokens": list(analysis.tokens), "matched": None}
        scored.sort(key=lambda t: t[:3], reverse=True)
        best = scored[0]
        ties = [t[3].id for t in scored[1:] if t[:2] == best[:2]]
        return best[3], {"tokens": list(analysis.tokens), "matched": best[3].id, "priority": best[0],
                         "specificity": best[1], "ties": ties}

    def respond(self, state, turn_input):
        if isinstance(turn_input, Utterance):
            pattern, trace = self.match(turn_input.text)
        else:
            pattern, trace = None, {"matched": None, "note": f"{type(turn_input).__name__} is not handled by FAQ rules"}
        if pattern is not None:
            meta = {**state.meta, MISSES: 0}
            return DMResult(self.pack.answers[pattern.id], state.evolve(meta=meta), trace={"rule": pattern.id, **trace})
        fb = self.pack.fallback
        misses = int(state.meta.get(MISSES, 0)) + 1
        new_state = state.evolve(meta={**state.meta, MISSES: misses})
        trace = {"rule": "fallback", "misses": misses, **trace}
        if misses >= fb.max_misses:
            action = HandOff("no_match") if fb.on_exceed == "handoff" else EndCall()
            return DMResult(fb.exceed_reply, new_state, actions=(action,), trace={**trace, "escalated": fb.on_exceed})
        return DMResult(fb.reply, new_state, trace=trace)


def default_factory(ctx):
    from ..evaluate import DEFAULT_DOMAINS_DIR
    return FaqRuleManager(_pack(DEFAULT_DOMAINS_DIR, ctx.domain, ctx.lang))


_PACKS: dict = {}


def _pack(domains_dir: str, domain: str, lang: str) -> DomainPack:
    key = (domains_dir, domain, lang)
    if key not in _PACKS:  # packs are immutable, so one load per domain and language is enough
        _PACKS[key] = DomainPack.load(domains_dir, domain, lang)
    return _PACKS[key]
