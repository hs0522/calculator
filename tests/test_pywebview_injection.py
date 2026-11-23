"""pywebview 5.4 가 `window.pywebview.api` 를 실제로 만들어 내는지 검증한다.

pywebview 5.4 는 `parse_api_js` 대신 `webview/util.py` 의 inject_pywebview 안
`get_functions()` 로 js_api 객체의 public 멤버를 훑는다. 이름이 `_` 로 시작하지
않는 속성이 있으면 그 객체를 재귀 탐색하는데, 위젯·창·WinForms 객체까지 들어가
예외가 나면 finish 스크립트가 주입되지 않아 api 가 통째로 비어 버린다
(v1.0.2 에서 계산·닫기 버튼이 모두 먹통이 된 원인).
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app  # noqa: E402

EXPECTED_FUNCS = {
    "version", "minimize", "close", "set_on_top", "get_window_state",
    "check_update", "open_release", "presets", "date_calc", "refund_calc", "copy",
}

try:  # 윈도우 CI(requirements.txt)에는 들어 있고, 개발 환경에는 없을 수 있다.
    import webview  # noqa: F401
    from webview import util as webview_util

    HAVE_WEBVIEW = True
except Exception:  # noqa: BLE001
    HAVE_WEBVIEW = False


class _StandInWidget:
    """실제 창 없이 Api 만 만들기 위한 최소 위젯."""

    def __init__(self):
        self.window = None
        self.always_on_top = True

    def run(self):  # pywebview 가 재귀 탐색했을 때 흔적을 남기는 public 메서드
        return None


def get_functions_like_pywebview_54(js_api):
    """pywebview 5.4 util.inject_pywebview 의 get_functions 와 같은 알고리즘."""
    exposed_objects = []
    functions = {}

    def walk(obj, base_name=""):
        if obj in exposed_objects:
            return
        exposed_objects.append(obj)
        for name in dir(obj):
            full_name = f"{base_name}.{name}" if base_name else name
            if name.startswith("_"):
                continue
            attr = getattr(obj, name)
            if callable(attr):
                functions[full_name] = True
            elif isinstance(attr, object) and hasattr(attr, "__module__"):
                walk(attr, full_name)  # pywebview 는 여기서 창·GUI 객체까지 파고든다

    walk(js_api)
    return functions


class TestApiSurface(unittest.TestCase):
    def test_no_public_non_method_attributes(self):
        api = app.Api(_StandInWidget())
        offenders = [
            name
            for name in dir(api)
            if not name.startswith("_") and not callable(getattr(api, name, None))
        ]
        self.assertEqual(offenders, [], "pywebview 가 재귀 탐색할 public 속성이 있습니다")

    def test_widget_reference_is_private(self):
        api = app.Api(_StandInWidget())
        self.assertFalse(hasattr(api, "widget"))
        self.assertIsNotNone(api._widget)

    def test_func_list_is_flat_and_complete(self):
        api = app.Api(_StandInWidget())
        names = set(get_functions_like_pywebview_54(api))
        self.assertEqual(names, EXPECTED_FUNCS)
        self.assertEqual([n for n in names if "." in n], [], "중첩 함수명은 api 객체를 오염시킨다")
        # finish.js 는 이 목록을 JSON 으로 박아 넣는다.
        json.dumps([{"func": n, "params": []} for n in sorted(names)])


class _Event:
    def set(self):
        pass


class _Events:
    before_load = _Event()
    _pywebviewready = _Event()
    loaded = _Event()
    shown = _Event()


class _FakeWindow:
    """inject_pywebview 가 건드리는 속성만 가진 가짜 Window."""

    def __init__(self, js_api):
        self._js_api = js_api
        self._functions = {}
        self._expose_lock = threading.Lock()
        self.uid = "test-window"
        self.js_api_endpoint = None
        self.text_select = True
        self.zoomable = False
        self.draggable = False
        self.easy_drag = False
        self.frameless = True
        self.events = _Events()
        self.scripts = []
        self.injected = threading.Event()

    def run_js(self, script):
        self.scripts.append(script)
        if "_createApi(JSON.parse" in script:
            self.injected.set()


@unittest.skipUnless(HAVE_WEBVIEW, "pywebview 가 설치되어 있지 않습니다")
class TestRealPywebviewInjection(unittest.TestCase):
    def _run_injection(self, api):
        window = _FakeWindow(api)
        webview_util.inject_pywebview("edgechromium", window)
        return window

    def _inject(self, api):
        window = self._run_injection(api)
        self.assertTrue(window.injected.wait(5), "finish 스크립트가 주입되지 않았습니다")
        script = [s for s in window.scripts if "_createApi(JSON.parse" in s][0]
        raw = re.search(r"JSON\.parse\('(.*?)'\)\);", script, re.S).group(1)
        return json.loads(raw)

    def test_api_functions_are_injected(self):
        funcs = self._inject(app.Api(_StandInWidget()))
        names = {f["func"] for f in funcs}
        self.assertEqual(names, EXPECTED_FUNCS)

    def test_parameters_are_exposed(self):
        funcs = {f["func"]: f["params"] for f in self._inject(app.Api(_StandInWidget()))}
        self.assertEqual(funcs["date_calc"], ["payload"])
        self.assertEqual(funcs["refund_calc"], ["payload"])
        self.assertEqual(funcs["set_on_top"], ["value"])
        self.assertEqual(funcs["copy"], ["text"])

    def test_widget_object_does_not_leak_into_api(self):
        """v1.0.2 처럼 Api.widget 이 public 이면 재귀 탐색으로 목록이 오염된다."""
        class LeakyApi(app.Api):
            pass

        leaky = LeakyApi(_StandInWidget())
        leaky.widget = _StandInWidget()  # 회귀 재현용(실제 코드에는 없음)
        names = {f["func"] for f in self._inject(leaky)}
        self.assertTrue(EXPECTED_FUNCS.issubset(names))
        self.assertTrue(
            any(n.startswith("widget.") for n in names),
            "재귀 탐색이 일어나지 않으면 이 회귀 테스트가 의미를 잃는다",
        )

    def test_raising_attribute_kills_the_whole_bridge(self):
        """재귀 탐색 중 예외가 나면 finish 스크립트가 아예 주입되지 않는다(빈 api)."""

        class Exploding:
            window = None

            def run(self):
                return None

            @property
            def boom(self):
                raise RuntimeError("cross-thread operation not valid")

        class LeakyApi(app.Api):
            pass

        leaky = LeakyApi(_StandInWidget())
        leaky.widget = Exploding()

        import logging

        logging.disable(logging.CRITICAL)
        try:
            window = self._run_injection(leaky)
            injected = window.injected.wait(3)
        finally:
            logging.disable(logging.NOTSET)
        self.assertFalse(injected, "예외가 나도 주입되면 이 회귀 재현은 의미가 없다")


class TestWindowControls(unittest.TestCase):
    def test_close_destroys_window_after_returning(self):
        class Window:
            def __init__(self):
                self.destroyed = threading.Event()

            def destroy(self):
                self.destroyed.set()

        class Widget:
            window = None
            always_on_top = True

        widget = Widget()
        widget.window = Window()
        api = app.Api(widget)
        self.assertTrue(api.close())
        self.assertTrue(widget.window.destroyed.wait(2), "창이 닫히지 않았습니다")
        self.assertTrue(api.close())  # 두 번 눌러도 예외 없이 True

    def test_minimize_without_window_is_safe(self):
        self.assertFalse(app.Api(_StandInWidget()).minimize())

    def test_minimize_calls_window(self):
        class Window:
            called = False

            def minimize(self):
                self.called = True

        class Widget:
            always_on_top = True

        widget = Widget()
        widget.window = Window()
        self.assertTrue(app.Api(widget).minimize())
        self.assertTrue(widget.window.called)

    def test_set_on_top_keeps_state(self):
        class Widget:
            always_on_top = False

            def apply_on_top(self, value):
                self.always_on_top = bool(value)
                return self.always_on_top

        widget = Widget()
        api = app.Api(widget)
        self.assertTrue(api.set_on_top(True))
        self.assertTrue(widget.always_on_top)
        self.assertEqual(api.get_window_state(), {"always_on_top": True})


if __name__ == "__main__":
    unittest.main()
