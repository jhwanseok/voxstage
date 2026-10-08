"""FAQ by keyword rules: question in, verbatim answer out (R1, ADR 0009).

Per entry: `all_of` (every group needs one of its words), `any_of` (at least one, if given), `none_of` (none),
`priority`, and `regex` as an alternative path for what a word group cannot say. The best match is the highest
priority, then the most specific (more matched words), then file order. No match is a miss; after
`max_misses` consecutive misses the manager hands off or ends the call, as configured.
"""

from __future__ import annotations

from typing import Optional

from ..dialogue import DialogueManager, DMResult, EndCall, HandOff
from ..domain_pack import DomainPack
from ..turn import Utterance
from .matching import Matcher
from .tokenize import Tokenizer, for_lang

MISSES = "faq_misses"


class FaqRuleManager(DialogueManager):
    name = "faq_rules"

    def __init__(self, pack: DomainPack, tokenizer: Optional[Tokenizer] = None):
        if pack.fallback is None:
            raise ValueError(f"{pack.domain}/{pack.lang}: no rules/config.yaml (fallback policy) in the pack")
        self.pack = pack
        self.tok = tokenizer or for_lang(pack.lang)
        self.matcher = Matcher(pack.patterns, self.tok)

    def match(self, text: str) -> tuple:
        return self.matcher.match(text)

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
