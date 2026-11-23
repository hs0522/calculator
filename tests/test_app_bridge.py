"""앱 창·JS 브리지 회귀 테스트 (python -m unittest).

윈도우 WebView2(pywebview)에서 부팅이 빨라 브리지가 붙기 전에 계산을 시도하면
"계산기를 불러오지 못했습니다" 오류가 뜨고 오른쪽 세로 스크롤바가 생겼다(v1.0.1).
그 두 가지가 되돌아가지 않도록 소스 수준에서 고정한다.
"""

from __future__ import annotations

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app  # noqa: E402
import calculator  # noqa: E402


def read_web() -> str:
    with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as fp:
        return fp.read()


class TestWindowSize(unittest.TestCase):
    def test_default_size_has_windows_slack(self):
        width, height = app.DEFAULT_SIZE
        # 336×456 에서 윈도우 기본 폰트 때문에 10~15px 모자라 스크롤바가 생겼다.
        self.assertGreaterEqual(width, 342)
        self.assertGreaterEqual(height, 478)

    def test_min_size(self):
        self.assertGreaterEqual(app.MIN_SIZE[0], 316)
        self.assertGreaterEqual(app.MIN_SIZE[1], 460)
        self.assertLessEqual(app.MIN_SIZE[0], app.DEFAULT_SIZE[0])
        self.assertLessEqual(app.MIN_SIZE[1], app.DEFAULT_SIZE[1])


class TestLocalEngineFallback(unittest.TestCase):
    """브리지가 없어도 계산되는 내장 엔진(v1.0.3)이 되돌아가지 않게 고정한다."""

    def test_local_calculators_exist(self):
        html = read_web()
        self.assertIn("function localDateCalc", html)
        self.assertIn("function localRefundCalc", html)
        self.assertIn("function localPresets", html)
        self.assertIn("const LOCAL_API =", html)
        self.assertIn("function localCall", html)

    def test_bridge_error_messages_are_gone(self):
        html = read_web()
        self.assertNotIn("계산기를 불러오지 못했습니다", html)
        self.assertNotIn("회원권 정보를 불러오지 못했습니다", html)

    def test_boot_does_not_wait_for_bridge(self):
        html = read_web()
        self.assertIn('document.addEventListener("DOMContentLoaded", () => { boot(); })', html)

    def test_presets_match_python(self):
        html = read_web()
        rows = re.findall(
            r'\{id: "(\w+)", kind: "(\w+)", sessions: (\d+), period_value: (\d+), '
            r'period_unit: "(\w+)", price: (\d+)\}',
            html,
        )
        parsed = [
            (pid, kind, int(sessions), int(value), unit, int(price))
            for pid, kind, sessions, value, unit, price in rows
        ]
        expected = [
            (p.id, p.kind, p.sessions, p.period_value, p.period_unit, p.price)
            for p in calculator.PRESETS
        ]
        self.assertEqual(parsed, expected)

    def test_rates_match_python(self):
        html = read_web()
        self.assertIn("const GROUP_RATE = 22000, PERSONAL_RATE = 77000;", html)
        self.assertIn("const PENALTY_RATE = 0.10;", html)


class TestJsBridge(unittest.TestCase):
    def test_every_api_called_from_js_exists(self):
        html = read_web()
        names = set(re.findall(r'call(?:Api|Window)\("([a-z_]+)"', html))
        self.assertIn("presets", names)
        self.assertIn("date_calc", names)
        self.assertIn("refund_calc", names)
        for name in sorted(names):
            self.assertTrue(callable(getattr(app.Api, name, None)), f"Api.{name} 가 없습니다")

    def test_boot_waits_for_pywebview_bridge(self):
        html = read_web()
        self.assertIn('window.addEventListener("pywebviewready", boot)', html)
        self.assertIn("waitForBridge(5000)", html)
        # 비어 있는 window.pywebview.api 를 준비 완료로 보면 안 된다.
        self.assertIn('typeof w.api.presets === "function"', html)
        # v1.0.1 의 성급한 부팅은 남아 있으면 안 된다.
        self.assertNotIn("if (!window.pywebview) boot();", html)
        self.assertNotIn("else setTimeout(boot, 1500);", html)

    def test_http_preview_still_boots_directly(self):
        html = read_web()
        self.assertIn("isHttpPreview()", html)
        self.assertIn('window.location.protocol.startsWith("http")', html)

    def test_call_api_retries_and_never_fetches_on_file(self):
        html = read_web()
        self.assertIn("waitForBridge(1500)", html)
        self.assertIn('if (isHttpPreview()) {', html)


class TestRefundNegativeDisplay(unittest.TestCase):
    """v1.0.4: 환불 불가를 `0원 (환불 불가)` 대신 빨간 `-금액원` 으로 보여 준다."""

    def test_old_placeholder_is_gone(self):
        html = read_web()
        self.assertNotIn("0원 (환불 불가)", html)
        self.assertNotIn("환불금액이 없습니다", html)

    def test_js_formats_negative_amount(self):
        html = read_web()
        self.assertIn("const isNegative = raw < 0;", html)
        self.assertIn('const refundText = isNegative ? "-" + won(Math.abs(raw)) : won(raw);', html)
        self.assertIn("is_negative: isNegative,", html)

    def test_big_amount_turns_red(self):
        html = read_web()
        self.assertIn(".big.is-negative{color:#DC2626;}", html)
        self.assertIn('bigEl.classList.toggle("is-negative", !!(opts && opts.negative));', html)
        self.assertIn("setBig(out.refund_text, {negative: !!out.is_negative});", html)

    def test_big_font_is_smaller_on_refund_tab(self):
        html = read_web()
        match = re.search(r"\.is-refund \.big\{font-size:(\d+)px;", html)
        self.assertIsNotNone(match, "환불 탭 금액 글자 크기 규칙이 없습니다")
        size = int(match.group(1))
        self.assertGreaterEqual(size, 22)
        self.assertLessEqual(size, 24)

    def test_python_and_js_show_the_same_text(self):
        """같은 입력에 파이썬과 화면 내장 계산이 같은 표기를 내도록 기대값을 고정한다."""
        html = read_web()
        # JS 금액 표기(쉼표 + 원)가 파이썬 format_won 과 같은 모양인지 확인한다.
        self.assertIn('Number(n).toLocaleString("ko-KR") + "원"', html)
        for paid, used, rate, expected in (
            (264_000, 5, 22_000, "127,600원"),
            (264_000, 12, 22_000, "-26,400원"),
            (100_000, 5, 22_000, "-20,000원"),
            (220_000, 9, 22_000, "0원"),
            (750_000, 10, 77_000, "-95,000원"),
        ):
            out = calculator.build_refund_result(str(paid), used, rate)
            self.assertEqual(out["refund_text"], expected)
            self.assertEqual(out["is_negative"], expected.startswith("-"))


if __name__ == "__main__":
    unittest.main()
