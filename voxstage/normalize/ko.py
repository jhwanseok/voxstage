"""Korean spoken numbers, days and dates, only what the datasets need (R11-1).

Works on the raw text, word (어절) by word, without the morphological analyzer: a numeral run at the start of a word
counts only when the rest of the word is empty, a unit or counter, a particle, 일 (day) or 월 (month), so 이체, 오전,
사람 and 이번 are never numbers. Native numerals (두, 세, ...) count only before a counter, so 네 (yes) is never four.
"""

from __future__ import annotations

import re
from typing import Optional

from . import dates as D

DIGITS = {"영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9}
SMALL_UNITS = {"십": 10, "백": 100, "천": 1000}
NUMERAL_CHARS = set(DIGITS) | set(SMALL_UNITS) | {"만"}
COUNTERS = ("개", "명", "장", "대", "권", "벌")
UNITS = ("달러", "불", "원", "기가", "짜리") + COUNTERS
PARTICLES = ("이라고", "이에요", "이예요", "예요", "이요", "라고", "으로", "부터", "까지", "이나", "정도", "쯤", "씩",
             "요", "로", "에", "은", "는", "이", "가", "을", "를", "도", "만", "고")
NATIVE = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7,
          "여덟": 8, "아홉": 9, "열": 10, "스무": 20, "스물": 20}
WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
WINDOWS = (("오전", "morning"), ("아침", "morning"), ("오후", "afternoon"), ("저녁", "evening"), ("밤", "evening"))

_PUNCT = re.compile(r"[.,!?~\"']")


def _sino(run: str) -> Optional[int]:
    """Sino-Korean cardinal (이천오백 -> 2500). Two digits in a row (사팔) are not a cardinal: they are read one by one."""
    total, section, current, seen = 0, 0, 0, False
    for k, ch in enumerate(run):
        if ch in DIGITS:
            if k > 0 and run[k - 1] in DIGITS:
                return None
            current, seen = DIGITS[ch], True
        elif ch in SMALL_UNITS:
            section += (current or 1) * SMALL_UNITS[ch]
            current, seen = 0, True
        elif ch == "만":
            total += (section + current or 1) * 10000
            section, current, seen = 0, 0, True
        else:
            return None
    return total + section + current if seen else None


def _rest_ok(rest: str) -> bool:
    return rest == "" or rest.startswith(UNITS + PARTICLES + ("일", "월"))


def _native(word: str, nxt: str) -> Optional[int]:
    """두 개, 두개, 열두 명: a native numeral right before a counter."""
    for form in sorted(NATIVE, key=len, reverse=True):
        for tens in ("", "열", "스물", "스무"):
            head = tens + form if tens and form not in ("열", "스무", "스물") else form
            if word.startswith(head):
                rest = word[len(head):]
                if (rest.startswith(COUNTERS)) or (rest == "" and nxt.startswith(COUNTERS)):
                    value = NATIVE[form] + ({"열": 10, "스물": 20, "스무": 20}.get(tens, 0))
                    return value
    return None


def scan(text: str) -> list:
    """Items in order: ("number", int), ("digits", str), ("day", int), ("month", int), ("weekday", int),
    ("word", str)."""
    ws = [w for w in _PUNCT.sub(" ", text).split() if w]
    out = []
    for i, w in enumerate(ws):
        nxt = ws[i + 1] if i + 1 < len(ws) else ""
        m = re.fullmatch(r"(\d[\d,]*)(.*)", w)
        if m:
            value, rest = int(m.group(1).replace(",", "")), m.group(2)
            if rest.startswith("일") and not rest.startswith("일요일"):
                out.append(("day", value))
            elif rest.startswith("월") and not rest.startswith("월요일"):
                out.append(("month", value))
            else:
                out.append(("number", value))
            continue
        if len(w) >= 3 and w[0] in WEEKDAYS and w[1:3] == "요일":
            out.append(("weekday", WEEKDAYS[w[0]]))
            continue
        native = _native(w, nxt)
        if native is not None:
            out.append(("number", native))
            continue
        k = 0
        while k < len(w) and w[k] in NUMERAL_CHARS:
            k += 1
        run, rest = w[:k], w[k:]
        # "사십이요" is 40 and a copula, not 42 and 요: a round number then 이 + an ending
        if len(run) >= 3 and run[-1] == "이" and run[-2] in SMALL_UNITS and rest.startswith(("요", "에요", "라고", "고")):
            run, rest = run[:-1], "이" + rest
        if not run or not _rest_ok(rest):
            out.append(("word", w))
            continue
        if rest.startswith("월") and not rest.startswith("월요일"):
            value = _sino(run)
            out.append(("month", value) if value else ("word", w))
            continue
        next_is_digit = len(nxt) == 1 and nxt in DIGITS
        if run == "일" and (rest or not next_is_digit) and rest[:1] in ("", "로", "에", "부", "까", "이", "은", "는", "을") \
                and out and out[-1][0] == "number":
            out[-1] = ("day", out[-1][1])   # "이십 일로": the day suffix after a spoken number
            continue
        if len(run) >= 2 and run[-1] == "일" and not rest.startswith(UNITS) and not nxt.startswith(UNITS):
            value = _sino(run[:-1])   # "십오일", "이십일에": in a day phrase the last 일 is the day
            if value and value <= 31:   # 천일 is 1001, not day 1000
                out.append(("day", value))
                continue
        if not all(ch in DIGITS for ch in run) and _sino(run) is None:   # "십삼삼": neither a cardinal nor digits
            out.append(("word", w))
            continue
        if all(ch in DIGITS for ch in run):
            if len(run) >= 2:   # "사팔이일": said digit by digit
                out.append(("digits", "".join(str(DIGITS[ch]) for ch in run)))
                continue
            if rest or nxt.startswith(UNITS):   # "오 개", "오개"
                out.append(("number", DIGITS[run]))
                continue
            out.append(("one", DIGITS[run]))   # a single digit word: part of a digit-by-digit run, or nothing
            continue
        out.append(("number", _sino(run)))
    merged = []
    for item in out:   # single digit words in a row: "일 오" -> 15
        if item[0] == "one" and merged and merged[-1][0] in ("one", "digits_run"):
            prev = merged.pop()
            merged.append(("digits_run", (prev[1] if prev[0] == "digits_run" else str(prev[1])) + str(item[1])))
        else:
            merged.append(item)
    result = []
    for kind, value in merged:
        if kind == "digits_run":
            result.append(("digits", value))
        elif kind == "one":
            result.append(("word", str(value)))
        else:
            result.append((kind, value))
    return result


def numbers(text: str) -> list:
    return [int(v) for kind, v in scan(text) if kind in ("number", "digits")]


def digit_string(text: str) -> Optional[str]:
    for kind, v in scan(text):
        if kind == "digits":
            return v
        if kind == "number":
            return str(v)
    return None


def day_of_month(text: str) -> Optional[int]:
    for kind, v in scan(text):
        if kind == "day" and 1 <= v <= 31:
            return v
    return None


def _compact(text: str) -> str:
    return text.replace(" ", "")


def month_start(text: str, now) -> Optional[D.DateValue]:
    today, c = D.clock(now), _compact(text)
    if "다음달" in c:
        return D.DateValue(D.add_months(today, 1).isoformat(), "first day of next month")
    if "이번달" in c:
        return D.DateValue(D.add_months(today, 0).isoformat(), "first day of this month")
    for kind, v in scan(text):
        if kind == "month" and 1 <= v <= 12:
            year = today.year if v >= today.month else today.year + 1
            return D.DateValue(f"{year:04d}-{v:02d}-01", "first day of the named month, not in the past")
    return None


def date(text: str, now):
    today, c, items = D.clock(now), _compact(text), scan(text)
    for word, days in (("모레", 2), ("내일", 1), ("오늘", 0)):
        if word in c:
            return D.relative_day(today, days)
    for kind, v in items:
        if kind == "weekday":
            this_week = D.weekday_this_week(today, v)
            if "다음주" in c:
                return D.DateValue((this_week + D.dt.timedelta(days=7)).isoformat(), "다음 주: the next calendar week")
            if "이번주" in c and this_week >= today:
                return D.DateValue(this_week.isoformat(), "이번 주: this calendar week")
            return D.nearest_weekday(today, v)
    day = next((v for kind, v in items if kind == "day"), None)
    month = next((v for kind, v in items if kind == "month"), None)
    if day is not None and month is not None:
        return D.nearest_month_day(today, month, day)
    if day is not None:
        if "다음달" in c:
            return D.in_month(today, 1, day)
        if "이번달" in c:
            return D.in_month(today, 0, day)
        return D.nearest_day(today, day)
    return None


def time_window(text: str) -> Optional[str]:
    for word, window in WINDOWS:
        if word in text:
            return window
    return None
