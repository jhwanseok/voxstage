"""Tokenisation for rule matching (ADR 0009 for English, ADR 0011 for Korean).

`analyze(text)` returns the tokens a pattern word can equal and a `joined` string (the tokens without spaces).
For Korean, a pattern word of two or more syllables also matches as a substring of `joined`, so "영업시간" and
"영업 시간" match the same pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Analysis:
    tokens: tuple
    joined: str


class Tokenizer:
    lang = ""

    def analyze(self, text: str) -> Analysis:
        raise NotImplementedError

    def has(self, analysis: Analysis, word: str) -> bool:
        """Does the pattern word occur in the analysed text?"""
        raise NotImplementedError


class EnglishTokenizer(Tokenizer):
    lang = "en"
    _WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

    def analyze(self, text: str) -> Analysis:
        tokens = tuple(self._WORD.findall(text.lower()))
        return Analysis(tokens, "".join(tokens))

    def has(self, analysis: Analysis, word: str) -> bool:
        return word.lower() in analysis.tokens


class KiwiTokenizer(Tokenizer):
    """Content morphemes from the Kiwi morphological analyzer (optional dependency `voxstage[ko]`)."""

    lang = "ko"
    CONTENT_TAGS = {"NNG", "NNP", "NR", "NP", "VV", "VA", "XR", "MAG", "SL", "SN"}

    def __init__(self):
        try:
            from kiwipiepy import Kiwi
        except ImportError as exc:  # fail with the fix, not a bare ImportError
            raise ImportError("Korean rules need kiwipiepy: pip install 'voxstage[ko]'") from exc
        self._kiwi = Kiwi()

    def analyze(self, text: str) -> Analysis:
        tokens = tuple(t.form for t in self._kiwi.tokenize(text) if t.tag.split("-")[0] in self.CONTENT_TAGS)
        return Analysis(tokens, "".join(tokens))

    def has(self, analysis: Analysis, word: str) -> bool:
        word = word.replace(" ", "")
        return word in analysis.tokens or (len(word) >= 2 and word in analysis.joined)


def kiwi_available() -> bool:
    try:
        import kiwipiepy  # noqa: F401
        return True
    except ImportError:
        return False


_CACHE: dict = {}


def for_lang(lang: str) -> Tokenizer:
    """Tokenizers hold no per-conversation state, so one instance per language is shared
    (loading the Korean analyzer takes seconds)."""
    if lang not in _CACHE:
        if lang == "en":
            _CACHE[lang] = EnglishTokenizer()
        elif lang == "ko":
            _CACHE[lang] = KiwiTokenizer()
        else:
            raise ValueError(f"no tokenizer for language {lang!r}")
    return _CACHE[lang]


if __name__ == "__main__":  # python -m voxstage.rules.tokenize <lang> "text": what a pattern word can match
    import sys
    a = for_lang(sys.argv[1]).analyze(sys.argv[2])
    print(a.tokens, a.joined)
