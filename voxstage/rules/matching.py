"""Word-group matching shared by FAQ rules (R1) and flow triggers (R2).

A pattern matches when every `all_of` group has one of its words, at least one `any_of` word is present (if the
list is non-empty), and no `none_of` word is present; a `regex` is an alternative path. The best match is the
highest priority, then the most matched words, then file order.
"""

from __future__ import annotations

import re
from typing import Optional

from ..domain_pack import Pattern
from .tokenize import Tokenizer


class Matcher:
    def __init__(self, patterns, tokenizer: Tokenizer):
        self.patterns, self.tok = tuple(patterns), tokenizer
        self._regex = {p.id: tuple(re.compile(r, re.IGNORECASE) for r in p.regex) for p in self.patterns}

    def score(self, p: Pattern, text: str, analysis) -> Optional[int]:
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
        for order, p in enumerate(self.patterns):
            s = self.score(p, text, analysis)
            if s is not None:
                scored.append((p.priority, s, -order, p))
        if not scored:
            return None, {"tokens": list(analysis.tokens), "matched": None}
        scored.sort(key=lambda t: t[:3], reverse=True)
        best = scored[0]
        ties = [t[3].id for t in scored[1:] if t[:2] == best[:2]]
        return best[3], {"tokens": list(analysis.tokens), "matched": best[3].id, "priority": best[0],
                         "specificity": best[1], "ties": ties}
