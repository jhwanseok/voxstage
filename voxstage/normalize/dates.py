"""Calendar helpers shared by the languages: the scenario clock decides, the rule used is returned (R11-2)."""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DateValue:
    iso: str
    rule: str          # which fixed rule produced it, for the trace


@dataclass(frozen=True)
class Ambiguous:
    first: str
    second: str
    rule: str


def clock(now) -> dt.date:
    """`setup.now` as a date ("2026-10-05T09:00:00", "2026-10-05", or a date)."""
    if isinstance(now, dt.datetime):
        return now.date()
    if isinstance(now, dt.date):
        return now
    return dt.date.fromisoformat(str(now)[:10])


def add_months(day: dt.date, months: int) -> dt.date:
    """The first day of the month `months` after the month of `day`."""
    index = day.year * 12 + day.month - 1 + months
    return dt.date(index // 12, index % 12 + 1, 1)


def valid(year: int, month: int, day: int) -> Optional[dt.date]:
    if 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]:
        return dt.date(year, month, day)
    return None


def nearest_day(today: dt.date, day: int) -> Optional[DateValue]:
    """A day of the month without a month: the nearest such date not in the past."""
    for step in range(0, 13):
        first = add_months(today, step)
        d = valid(first.year, first.month, day)
        if d is not None and d >= today:
            return DateValue(d.isoformat(), "day without a month: nearest date not in the past")
    return None


def nearest_month_day(today: dt.date, month: int, day: int) -> Optional[DateValue]:
    """A month and a day without a year: the nearest such date not in the past."""
    for year in (today.year, today.year + 1):
        d = valid(year, month, day)
        if d is not None and d >= today:
            return DateValue(d.isoformat(), "month and day without a year: nearest date not in the past")
    return None


def in_month(today: dt.date, months_ahead: int, day: int) -> Optional[DateValue]:
    first = add_months(today, months_ahead)
    d = valid(first.year, first.month, day)
    return DateValue(d.isoformat(), f"day {day} of the month {months_ahead} ahead") if d else None


def weekday_this_week(today: dt.date, weekday: int) -> dt.date:
    """Weeks start on Monday."""
    return today + dt.timedelta(days=weekday - today.weekday())


def nearest_weekday(today: dt.date, weekday: int) -> DateValue:
    ahead = (weekday - today.weekday()) % 7
    return DateValue((today + dt.timedelta(days=ahead)).isoformat(), "weekday: nearest not in the past")


def relative_day(today: dt.date, days: int) -> DateValue:
    return DateValue((today + dt.timedelta(days=days)).isoformat(), f"today plus {days} days")
