"""R11: spoken numbers, days, dates and times (tables). Run: python -m unittest discover -s tests -v"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import normalize as N

NOW = "2026-10-05T09:00:00"   # a Monday, the clock of the C07 scenarios

NUMBERS = [
    ("en", "Transfer thirty dollars please", [30]),
    ("en", "Transfer thirteen dollars please", [13]),
    ("en", "What is the fee if I transfer five hundred dollars", [500]),
    ("en", "twenty five hundred dollars", [2500]),
    ("en", "two thousand five hundred", [2500]),
    ("en", "a hundred dollars", [100]),
    ("en", "Change the quantity to fifty", [50]),
    ("en", "No fifteen one five", [15, 15]),
    ("en", "No forty not fourteen", [40, 14]),
    ("en", "four eight two one", [4821]),
    ("en", "$2,500 please", [2500]),
    ("en", "the fifteenth of next month", []),          # a day, not a number
    ("en", "Deliver two of them", [2]),
    ("en", "I want the forty gigabyte plan", [40]),
    ("ko", "삼십 달러 이체해 주세요", [30]),
    ("ko", "십삼 달러 이체해 주세요", [13]),
    ("ko", "오백 달러 이체하면 수수료가 얼마예요", [500]),
    ("ko", "이천오백 달러", [2500]),
    ("ko", "수량을 오십 개로 바꿔 주세요", [50]),
    ("ko", "아니요 십오요 일 오 십오 개요", [15, 15, 15]),
    ("ko", "아니요 십사 말고 사십이요", [14, 40]),        # 사십이요: forty and a copula
    ("ko", "사십 기가 요금제로 할게요", [40]),
    ("ko", "40기가예요", [40]),
    ("ko", "두 개 내일 오전에 보내 주세요", [2]),
    ("ko", "십일 달러", [11]),
    ("ko", "사팔이일", [4821]),
    ("ko", "사 팔 이 일", [4821]),
    ("ko", "다음 달 십오일에 이천오백 달러", [2500]),     # 십오일 is a day
    ("ko", "네 맞아요", []),                               # 네 is yes, not four
    ("ko", "이체하려고 하는데요", []),                     # 이 in 이체 is not two
    ("ko", "오전에 사람이랑 이번 주에", []),
]

DIGIT_STRINGS = [
    ("en", "four eight two one", "4821"), ("en", "zero zero one", "001"), ("en", "1001", "1001"),
    ("ko", "사팔이일", "4821"), ("ko", "공공일", "001"), ("ko", "일 공 공 일", "1001"),
]

DAYS = [
    ("en", "the twentieth starting next month", 20), ("en", "on the 15th", 15), ("en", "the twenty first", 21),
    ("en", "thirty dollars", None),
    ("ko", "청구일을 이십 일로", 20), ("ko", "이십일에", 20), ("ko", "20일로", 20), ("ko", "십일일에", 11),
    ("ko", "십일 달러", None),
]

DATES = [
    ("en", "for the fifteenth of next month", "2026-11-15"),
    ("en", "tomorrow morning", "2026-10-06"),
    ("en", "the day after tomorrow", "2026-10-07"),
    ("en", "on November fifteenth", "2026-11-15"),
    ("en", "on November 15", "2026-11-15"),
    ("en", "on the 15th", "2026-10-15"),
    ("en", "on the 2nd", "2026-11-02"),                    # already past this month: next month
    ("en", "on Friday", "2026-10-09"),
    ("en", "next Monday", "2026-10-12"),
    ("en", "in September on the 3rd", "2027-09-03"),     # month and day passed this year: next year
    ("ko", "다음 달 십오일에", "2026-11-15"),
    ("ko", "내일 오전에", "2026-10-06"),
    ("ko", "모레요", "2026-10-07"),
    ("ko", "십일월 십오일에", "2026-11-15"),
    ("ko", "15일에", "2026-10-15"),
    ("ko", "이일에", "2026-11-02"),
    ("ko", "다음 주 화요일에", "2026-10-13"),
    ("ko", "금요일에", "2026-10-09"),
]

MONTH_STARTS = [
    ("en", "starting next month", "2026-11-01"), ("en", "from November", "2026-11-01"),
    ("en", "from March", "2027-03-01"), ("en", "this month", "2026-10-01"),
    ("ko", "다음 달부터", "2026-11-01"), ("ko", "다음달부터요", "2026-11-01"), ("ko", "삼월부터", "2027-03-01"),
]

WINDOWS = [
    ("en", "tomorrow morning", "morning"), ("en", "in the afternoon", "afternoon"), ("en", "at night", "evening"),
    ("en", "tomorrow", None),
    ("ko", "내일 오전에", "morning"), ("ko", "아침에", "morning"), ("ko", "오후에", "afternoon"), ("ko", "저녁에", "evening"),
]


class NormalizeTables(unittest.TestCase):
    def test_numbers(self):
        for lang, text, expected in NUMBERS:
            self.assertEqual(N.numbers(text, lang), expected, (lang, text))

    def test_digit_strings(self):
        for lang, text, expected in DIGIT_STRINGS:
            self.assertEqual(N.digit_string(text, lang), expected, (lang, text))

    def test_days(self):
        for lang, text, expected in DAYS:
            self.assertEqual(N.day_of_month(text, lang), expected, (lang, text))

    def test_dates(self):
        for lang, text, expected in DATES:
            result = N.date(text, lang, NOW)
            self.assertEqual(result.iso if result else None, expected, (lang, text))
            if result:
                self.assertTrue(result.rule, (lang, text))   # the rule used is always given (R11-2)

    def test_month_starts(self):
        for lang, text, expected in MONTH_STARTS:
            self.assertEqual(N.month_start(text, lang, NOW).iso, expected, (lang, text))

    def test_time_windows(self):
        for lang, text, expected in WINDOWS:
            self.assertEqual(N.time_window(text, lang), expected, (lang, text))


class AmbiguityTest(unittest.TestCase):
    def test_next_or_this_weekday_ahead_this_week_has_two_readings(self):
        for text in ("next Tuesday", "this Tuesday", "next Sunday"):
            result = N.date(text, "en", NOW)
            self.assertIsInstance(result, N.Ambiguous, text)
        result = N.date("next Tuesday", "en", NOW)
        self.assertEqual((result.first, result.second), ("2026-10-06", "2026-10-13"))

    def test_korean_next_week_is_not_ambiguous(self):
        self.assertIsInstance(N.date("다음 주 화요일", "ko", NOW), N.DateValue)

    def test_unknown_language(self):
        with self.assertRaises(ValueError):
            N.numbers("x", "fr")


class SelfContainedTest(unittest.TestCase):
    def test_the_package_imports_nothing_else_from_voxstage(self):
        folder = os.path.join(os.path.dirname(__file__), "..", "voxstage", "normalize")
        for name in os.listdir(folder):
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    text = f.read()
                self.assertNotIn("from ..", text, name)
                self.assertNotIn("import voxstage", text, name)


if __name__ == "__main__":
    unittest.main()
