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


if __name__ == "__main__":
    unittest.main()
