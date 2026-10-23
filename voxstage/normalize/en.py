"""English spoken numbers, days and dates, only what the datasets need (R11-1)."""

from __future__ import annotations

import re
from typing import Optional

from . import dates as D

UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
            "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
            "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
            "twentieth": 20, "thirtieth": 30}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
WEEKDAYS = {d: i for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                                        "sunday"])}
WINDOWS = {"morning": "morning", "afternoon": "afternoon", "evening": "evening", "night": "evening"}

_WORD = re.compile(r"\d[\d,]*(?:st|nd|rd|th)?|[a-z]+(?:'[a-z]+)?")


def words(text: str) -> list:
    return _WORD.findall(text.lower().replace("-", " "))


def _is_number_word(w: str) -> bool:
    return w in UNITS or w in TEENS or w in TENS or w in SCALES


def _cardinal(seq: list) -> int:
    total, current = 0, 0
    for w in seq:
        if w in UNITS:
            current += UNITS[w]
        elif w in TEENS:
            current += TEENS[w]
        elif w in TENS:
            current += TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        elif w == "thousand":
            total += (current or 1) * 1000
            current = 0
    return total + current


def _follows(prev: str, word: str) -> bool:
    """Can `word` continue the number that `prev` is part of? ("twenty five" yes, "thirteen thirty" no)."""
    if word in SCALES:
        return prev not in SCALES or (prev == "hundred" and word == "thousand")
    if prev in SCALES:
        return True
    if prev in TENS:
        return word in UNITS and word not in ("zero", "oh")
    return False


def _split_numbers(seq: list) -> list:
    """Cardinals where the grammar of English numbers allows; units said one by one become one digit string."""
    chunks, current = [], []
    for w in seq:
        if current and not _follows(current[-1], w):
            chunks.append(current)
            current = []
        current.append(w)
    if current:
        chunks.append(current)
    out, run = [], []
    for chunk in chunks + [None]:
        if chunk is not None and len(chunk) == 1 and chunk[0] in UNITS:
            run.append(chunk[0])
            continue
        if run:
            out.append(("digits", "".join(str(UNITS[x]) for x in run)) if len(run) >= 2
                       else ("number", UNITS[run[0]]))
            run = []
        if chunk is not None:
            out.append(("number", _cardinal(chunk)))
    return out


def _ordinal_at(ws: list, i: int) -> Optional[tuple]:
    """(day, next index) for "fifteenth", "twenty first", "15th" at position i."""
    w = ws[i]
    m = re.fullmatch(r"(\d+)(st|nd|rd|th)", w)
    if m:
        return int(m.group(1)), i + 1
    if w in ORDINALS:
        return ORDINALS[w], i + 1
    if w in TENS and i + 1 < len(ws) and ws[i + 1] in ORDINALS and ORDINALS[ws[i + 1]] < 10:
        return TENS[w] + ORDINALS[ws[i + 1]], i + 2
    return None


def scan(text: str) -> list:
    """Items in order: ("number", int), ("digits", str), ("day", int), ("word", str)."""
    ws, out, i = words(text), [], 0
    while i < len(ws):
        w = ws[i]
        ordinal = _ordinal_at(ws, i)
        if ordinal is not None:
            out.append(("day", ordinal[0]))
            i = ordinal[1]
            continue
        if re.fullmatch(r"\d[\d,]*", w):
            out.append(("number", int(w.replace(",", ""))))
            i += 1
            continue
        if _is_number_word(w) or (w == "a" and i + 1 < len(ws) and ws[i + 1] in SCALES):
            j = i
            while j < len(ws) and (_is_number_word(ws[j]) or ws[j] in ("a", "and")) and _ordinal_at(ws, j) is None:
                j += 1
            seq = [x for x in ws[i:j] if x not in ("a", "and")]
            out.extend(_split_numbers(seq))
            i = j if j > i else i + 1
            continue
        out.append(("word", w))
        i += 1
    return out


def numbers(text: str) -> list:
    """Every number that is not a day of the month, in order."""
    return [int(v) for kind, v in scan(text) if kind in ("number", "digits")]


def digit_string(text: str) -> Optional[str]:
    for kind, v in scan(text):
        if kind == "digits":
            return v
        if kind == "number":
            return str(v)
    return None


def day_of_month(text: str) -> Optional[int]:
    items = scan(text)
    for idx, (kind, v) in enumerate(items):
        if kind == "day" and 1 <= v <= 31:
            return v
        if kind == "word" and v == "the" and idx + 1 < len(items) and items[idx + 1][0] == "number" \
                and 1 <= items[idx + 1][1] <= 31:
            return items[idx + 1][1]
    return None


def month_start(text: str, now) -> Optional[D.DateValue]:
    today, ws = D.clock(now), words(text)
    for i, w in enumerate(ws):
        if w == "month" and i > 0 and ws[i - 1] in ("next", "this"):
            first = D.add_months(today, 1 if ws[i - 1] == "next" else 0)
            return D.DateValue(first.isoformat(), f"first day of {ws[i - 1]} month")
        if w in MONTHS:
            year = today.year if MONTHS[w] >= today.month else today.year + 1
            return D.DateValue(f"{year:04d}-{MONTHS[w]:02d}-01", "first day of the named month, not in the past")
    return None


def date(text: str, now):
    """An ISO date (DateValue), an Ambiguous pair, or None."""
    today, ws, items = D.clock(now), words(text), scan(text)
    if "tomorrow" in ws:
        if "after" in ws:   # the day after tomorrow
            return D.relative_day(today, 2)
        return D.relative_day(today, 1)
    if "today" in ws:
        return D.relative_day(today, 0)
    for i, w in enumerate(ws):
        if w in WEEKDAYS:
            wd = WEEKDAYS[w]
            before = ws[i - 1] if i > 0 else ""
            this_week = D.weekday_this_week(today, wd)
            if before in ("next", "this") and this_week > today:
                second = this_week + D.dt.timedelta(days=7)
                return D.Ambiguous(this_week.isoformat(), second.isoformat(),
                                   f"\"{before} {w}\" while {w} is still ahead this week: two readings")
            if before == "next":   # the weekday is today or behind us this week: next week's
                return D.DateValue((this_week + D.dt.timedelta(days=7)).isoformat(), f"\"next {w}\": next week")
            return D.nearest_weekday(today, wd)
    day = None
    for kind, v in items:
        if kind == "day":
            day = v
            break
    for i, w in enumerate(ws):
        if w in MONTHS:
            d = day
            if d is None:   # "November 15"
                for kind, v in scan(" ".join(ws[i + 1:i + 3])):
                    if kind == "number" and 1 <= v <= 31:
                        d = v
                        break
            if d is not None:
                return D.nearest_month_day(today, MONTHS[w], d)
    if day is not None:
        if "month" in ws:
            k = ws.index("month")
            if k > 0 and ws[k - 1] == "next":
                return D.in_month(today, 1, day)
            if k > 0 and ws[k - 1] == "this":
                return D.in_month(today, 0, day)
        return D.nearest_day(today, day)
    return None


def time_window(text: str) -> Optional[str]:
    for w in words(text):
        if w in WINDOWS:
            return WINDOWS[w]
    return None
