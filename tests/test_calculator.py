"""calculator.py 전수 테스트 (python -m unittest)."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calculator as c  # noqa: E402


class TestAddMonths(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(c.add_months(date(2026, 11, 23), 1), date(2026, 12, 23))
        self.assertEqual(c.add_months(date(2026, 11, 23), 2), date(2027, 1, 23))

    def test_year_rollover(self):
        self.assertEqual(c.add_months(date(2026, 12, 15), 1), date(2027, 1, 15))

    def test_month_end_clamp(self):
        self.assertEqual(c.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(c.add_months(date(2026, 3, 31), 1), date(2026, 4, 30))

    def test_leap_year_clamp(self):
        self.assertEqual(c.add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(c.add_months(date(2024, 2, 29), 12), date(2025, 2, 28))

    def test_twelve_months(self):
        self.assertEqual(c.add_months(date(2026, 11, 23), 12), date(2027, 11, 23))


class TestExpiryMonths(unittest.TestCase):
    def test_one_month(self):
        # 2026-11-23 + 1개월 - 1일
        self.assertEqual(c.calculate_expiry(date(2026, 11, 23), 1, "months"), date(2026, 12, 22))

    def test_two_months(self):
        self.assertEqual(c.calculate_expiry(date(2026, 11, 23), 2, "months"), date(2027, 1, 22))

    def test_presets_2_3_4_6_months(self):
        start = date(2026, 11, 23)
        self.assertEqual(c.calculate_expiry(start, 2, "months"), date(2027, 1, 22))
        self.assertEqual(c.calculate_expiry(start, 3, "months"), date(2027, 2, 22))
        self.assertEqual(c.calculate_expiry(start, 4, "months"), date(2027, 3, 22))
        self.assertEqual(c.calculate_expiry(start, 6, "months"), date(2027, 5, 22))

    def test_month_end_start(self):
        # 1/31 + 1개월 -> 2/28 보정, -1일 -> 2/27
        self.assertEqual(c.calculate_expiry(date(2027, 1, 31), 1, "months"), date(2027, 2, 27))

    def test_feb_29_start(self):
        self.assertEqual(c.calculate_expiry(date(2024, 2, 29), 12, "months"), date(2025, 2, 27))

    def test_inclusive_day_count(self):
        start = date(2026, 11, 23)
        expiry = c.calculate_expiry(start, 1, "months")
        self.assertEqual(c.total_days(start, expiry), 30)

    def test_single_day_when_zero_like(self):
        # 기간 1개월이라도 시작일이 1일이 아니면 하루는 남는다
        start = date(2026, 3, 1)
        self.assertEqual(c.calculate_expiry(start, 1, "months"), date(2026, 3, 31))


class TestExpiryWeeks(unittest.TestCase):
    def test_ten_weeks(self):
        self.assertEqual(c.calculate_expiry(date(2026, 11, 23), 10, "weeks"), date(2027, 1, 31))

    def test_twenty_weeks(self):
        self.assertEqual(c.calculate_expiry(date(2026, 11, 23), 20, "weeks"), date(2027, 4, 11))

    def test_one_week_is_seven_days(self):
        start = date(2026, 11, 23)
        expiry = c.calculate_expiry(start, 1, "weeks")
        self.assertEqual(expiry, date(2026, 11, 29))
        self.assertEqual(c.total_days(start, expiry), 7)

    def test_week_crosses_leap_day(self):
        self.assertEqual(c.calculate_expiry(date(2024, 2, 20), 2, "weeks"), date(2024, 3, 4))


class TestExpiryValidation(unittest.TestCase):
    def test_zero_value(self):
        with self.assertRaises(c.CalcError):
            c.calculate_expiry(date(2026, 11, 23), 0, "months")

    def test_negative_value(self):
        with self.assertRaises(c.CalcError):
            c.calculate_expiry(date(2026, 11, 23), -2, "weeks")

    def test_bad_unit(self):
        with self.assertRaises(c.CalcError):
            c.calculate_expiry(date(2026, 11, 23), 2, "days")

    def test_float_value(self):
        with self.assertRaises(c.CalcError):
            c.calculate_expiry(date(2026, 11, 23), 1.5, "months")  # type: ignore[arg-type]


class TestRefund(unittest.TestCase):
    def test_no_usage(self):
        r = c.calculate_refund(264_000, 0, 22_000, 12)
        self.assertEqual(r.penalty, 26_400)
        self.assertEqual(r.usage_deduction, 0)
        self.assertEqual(r.refund, 237_600)
        self.assertTrue(r.refundable)
        self.assertEqual(r.remaining_sessions, 12)

    def test_group_five_used(self):
        r = c.calculate_refund(264_000, 5, 22_000, 12)
        self.assertEqual(r.usage_deduction, 110_000)
        self.assertEqual(r.refund, 127_600)
        self.assertEqual(r.remaining_sessions, 7)

    def test_personal_rate(self):
        r = c.calculate_refund(750_000, 3, 77_000, 15)
        self.assertEqual(r.penalty, 75_000)
        self.assertEqual(r.usage_deduction, 231_000)
        self.assertEqual(r.refund, 444_000)

    def test_all_sessions_used_is_zero(self):
        r = c.calculate_refund(264_000, 12, 22_000, 12)
        self.assertEqual(r.refund, 0)
        self.assertFalse(r.refundable)

    def test_negative_floor(self):
        r = c.calculate_refund(100_000, 5, 22_000, 12)
        self.assertEqual(r.refund, 0)
        self.assertFalse(r.refundable)

    def test_exact_zero(self):
        r = c.calculate_refund(237_600, 10, 22_000, 12)
        self.assertEqual(r.refund, 0)
        self.assertFalse(r.refundable)

    def test_penalty_floor(self):
        # 123,456 * 10% = 12,345.6 -> 12,345 (절사)
        r = c.calculate_refund(123_456, 0, 22_000)
        self.assertEqual(r.penalty, 12_345)
        self.assertEqual(r.refund, 111_111)

    def test_no_sessions_given(self):
        r = c.calculate_refund(500_000, 1, 77_000)
        self.assertIsNone(r.remaining_sessions)
        self.assertEqual(r.refund, 373_000)

    def test_zero_paid(self):
        r = c.calculate_refund(0, 0, 22_000, 12)
        self.assertEqual(r.refund, 0)
        self.assertFalse(r.refundable)

    def test_used_over_sessions(self):
        with self.assertRaises(c.CalcError):
            c.calculate_refund(264_000, 13, 22_000, 12)

    def test_negative_used(self):
        with self.assertRaises(c.CalcError):
            c.calculate_refund(264_000, -1, 22_000, 12)

    def test_negative_paid(self):
        with self.assertRaises(c.CalcError):
            c.calculate_refund(-1, 0, 22_000, 12)


class TestParsers(unittest.TestCase):
    def test_amount_with_comma_and_won(self):
        self.assertEqual(c.parse_amount("264,000원"), 264_000)
        self.assertEqual(c.parse_amount(" 381800 "), 381_800)
        self.assertEqual(c.parse_amount(500_700), 500_700)

    def test_amount_empty(self):
        with self.assertRaises(c.CalcError):
            c.parse_amount("")

    def test_amount_not_number(self):
        with self.assertRaises(c.CalcError):
            c.parse_amount("이십이만")

    def test_amount_decimal(self):
        with self.assertRaises(c.CalcError):
            c.parse_amount("1000.5")

    def test_date_formats(self):
        self.assertEqual(c.parse_date("2026-11-23"), date(2026, 11, 23))
        self.assertEqual(c.parse_date("2026.11.23"), date(2026, 11, 23))
        self.assertEqual(c.parse_date("2026/11/23"), date(2026, 11, 23))

    def test_date_empty(self):
        with self.assertRaises(c.CalcError):
            c.parse_date("")

    def test_date_bad(self):
        with self.assertRaises(c.CalcError):
            c.parse_date("2026-13-01")

    def test_weekday_ko(self):
        self.assertEqual(c.weekday_ko(date(2027, 1, 22)), "금")
        self.assertEqual(c.weekday_ko(date(2026, 11, 23)), "월")


class TestBuilders(unittest.TestCase):
    def test_expiry_payload(self):
        out = c.build_expiry_result("2026-11-23", "2", "months", "6:1 그룹 12회")
        self.assertTrue(out["ok"])
        self.assertEqual(out["expiry"], "2027-01-22")
        self.assertEqual(out["expiry_text"], "2027-01-22(금)")
        self.assertEqual(out["total_days"], 61)
        self.assertIn("[6:1 그룹 12회]", out["guide_text"])
        self.assertIn("만료일 2027-01-22(금)", out["guide_text"])

    def test_refund_payload(self):
        out = c.build_refund_result("264,000", 5, 22_000, 12, "6:1 그룹 12회")
        self.assertTrue(out["ok"])
        self.assertEqual(out["refund"], 127_600)
        self.assertEqual(out["refund_text"], "127,600원")
        self.assertEqual(out["usage_detail"], "5회 × 22,000원")
        self.assertIn("[환불 내역] 6:1 그룹 12회", out["receipt_text"])

    def test_refund_payload_not_refundable(self):
        out = c.build_refund_result("100,000", 5, 22_000, 12)
        self.assertFalse(out["refundable"])
        self.assertEqual(out["refund_text"], "0원 (환불 불가)")

    def test_refund_payload_zero_paid(self):
        with self.assertRaises(c.CalcError):
            c.build_refund_result("", 0, 22_000, 12)


class TestPresets(unittest.TestCase):
    def test_preset_table(self):
        self.assertEqual(len(c.PRESETS), 7)
        g = [p for p in c.PRESETS if p.kind == "group"]
        p = [p for p in c.PRESETS if p.kind == "personal"]
        self.assertEqual([x.sessions for x in g], [12, 24, 36, 48])
        self.assertEqual([x.period_value for x in g], [2, 3, 4, 6])
        self.assertTrue(all(x.period_unit == "months" for x in g))
        self.assertTrue(all(x.per_session == 22_000 for x in g))
        self.assertEqual([x.sessions for x in p], [15, 20, 30])
        self.assertEqual([x.period_value for x in p], [10, 10, 20])
        self.assertTrue(all(x.period_unit == "weeks" for x in p))
        self.assertTrue(all(x.per_session == 77_000 for x in p))

    def test_preset_prices(self):
        self.assertEqual([x.price for x in c.PRESETS], [
            264_000, 381_800, 500_700, 571_600, 750_000, 1_200_000, 1_500_000,
        ])

    def test_preset_labels(self):
        self.assertEqual(c.PRESETS_BY_ID["g12"].label, "6:1 그룹 12회")
        self.assertEqual(c.PRESETS_BY_ID["p15"].period_label, "10주")

    def test_every_preset_expiry(self):
        for preset in c.PRESETS:
            expiry = c.calculate_expiry(date(2026, 11, 23), preset.period_value, preset.period_unit)
            self.assertGreater(expiry, date(2026, 11, 23))


if __name__ == "__main__":
    unittest.main(verbosity=2)
