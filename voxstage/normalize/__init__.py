"""Spoken numbers, days, dates and times to exact values (R11). Self-contained: imports nothing else from
`voxstage`, so it can become its own package later (decision R11-1). Dates resolve against a given clock with
fixed rules; the rule is returned so callers can trace it (decision R11-2)."""

from __future__ import annotations

from . import en, ko
from .dates import Ambiguous, DateValue

_LANGS = {"en": en, "ko": ko}


def _lang(lang: str):
    if lang not in _LANGS:
        raise ValueError(f"no normaliser for language {lang!r}")
    return _LANGS[lang]


def numbers(text: str, lang: str) -> list:
    return _lang(lang).numbers(text)


def digit_string(text: str, lang: str):
    return _lang(lang).digit_string(text)


def day_of_month(text: str, lang: str):
    return _lang(lang).day_of_month(text)


def date(text: str, lang: str, now):
    return _lang(lang).date(text, now)


def month_start(text: str, lang: str, now):
    return _lang(lang).month_start(text, now)


def time_window(text: str, lang: str):
    return _lang(lang).time_window(text)


__all__ = ["Ambiguous", "DateValue", "numbers", "digit_string", "day_of_month", "date", "month_start", "time_window"]
