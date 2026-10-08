"""Formatters for spoken values (R4, decision R4-1). A template picks one by name: `{result.fee | money(result.currency)}`.

How a number should be written depends on the TTS in use, so the choice lives in the flow data, not in the code
that renders it. Each formatter takes the value, the language and its arguments, and returns text. A new formatter
is one registered function; an unknown name in a flow is a load-time error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Callable

from .expr import ExprError


class FormatError(ExprError):
    """A value cannot be written the way the flow asked (unsupported currency, not a date, not a number)."""


@dataclass(frozen=True)
class Formatter:
    fn: Callable
    min_args: int = 0
    max_args: int = 0


FORMATTERS: dict = {}


def formatter(name: str, min_args: int = 0, max_args: int = 0):
    def deco(fn):
        FORMATTERS[name] = Formatter(fn, min_args, max_args)
        return fn
    return deco


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise FormatError(f"`{value!r}` is not a number")
    try:
        return float(value)
    except ValueError as exc:
        raise FormatError(f"`{value!r}` is not a number") from exc


def _grouped(value) -> str:
    n = _number(value)
    return f"{int(n):,}" if n == int(n) else f"{n:,.2f}"


@formatter("count")
def count(value, lang):
    return _grouped(value)


@formatter("money", 1, 1)
def money(value, lang, currency):
    """Amount and currency. USD and KRW only for now; the other currencies are backlog item D1."""
    amount = _grouped(value)
    table = {"en": {"USD": f"${amount}", "KRW": f"{amount} won"},
             "ko": {"USD": f"{amount}달러", "KRW": f"{amount}원"}}
    try:
        return table[lang][str(currency).upper()]
    except KeyError:
        raise FormatError(f"no way to say currency `{currency}` in `{lang}`") from None


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")


@formatter("date")
def date(value, lang):
    try:
        d = _date.fromisoformat(str(value))
    except ValueError:
        raise FormatError(f"`{value}` is not an ISO date (YYYY-MM-DD)") from None
    return f"{d.year}년 {d.month}월 {d.day}일" if lang == "ko" else f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"
