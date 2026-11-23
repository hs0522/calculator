"""클립보드 복사 회귀 테스트 (python -m unittest).

v1.0.3 까지 `복사` 버튼을 눌러도 아무것도 복사되지 않았다.
- app.py 의 ctypes 호출에 argtypes/restype 이 빠져 64비트 윈도우에서 핸들(포인터)이
  잘렸고, GlobalLock·SetClipboardData 가 조용히 실패했다.
- web/index.html 은 파이썬 브리지 복사를 먼저 시도해, 그 경로가 실패하면 끝이었다.

그 두 가지가 되돌아가지 않도록 고정한다.
"""

from __future__ import annotations

import ctypes
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app  # noqa: E402

SAMPLE = "정산 내역 127,600원\n최종 환불금액 -26,400원"


def read_app_source() -> str:
    with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fp:
        return fp.read()


def read_web() -> str:
    with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as fp:
        return fp.read()


def _read_clipboard():
    """테스트에서 클립보드 내용을 다시 읽어 온다(환경이 안 되면 None)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        if not user32.OpenClipboard(None):
            return None
        try:
            handle = user32.GetClipboardData(app.CF_UNICODETEXT)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        try:
            return root.clipboard_get()
        finally:
            root.destroy()
    except Exception:
        return None


class TestClipboardImplementation(unittest.TestCase):
    def test_win32_signatures_are_declared(self):
        """64비트 포인터 잘림 방지: 모든 Win32 함수에 argtypes/restype 이 있어야 한다."""
        src = read_app_source()
        for name in ("OpenClipboard", "EmptyClipboard", "SetClipboardData", "CloseClipboard"):
            self.assertIn(f"user32.{name}.argtypes", src)
            self.assertIn(f"user32.{name}.restype", src)
        for name in ("GlobalAlloc", "GlobalLock", "GlobalUnlock", "GlobalFree"):
            self.assertIn(f"kernel32.{name}.argtypes", src)
            self.assertIn(f"kernel32.{name}.restype", src)

    def test_handle_is_not_freed_after_success(self):
        """SetClipboardData 성공 뒤에는 클립보드가 메모리를 소유하므로 GlobalFree 하지 않는다."""
        src = read_app_source()
        self.assertIn("# 성공하면 클립보드가 이 메모리를 넘겨받는다", src)
        self.assertIn("        handle = None\n        return True", src)

    def test_open_clipboard_retries(self):
        src = read_app_source()
        self.assertGreaterEqual(app.CLIPBOARD_OPEN_RETRIES, 2)
        self.assertIn("for _ in range(CLIPBOARD_OPEN_RETRIES):", src)

    def test_powershell_fallback_uses_set_clipboard(self):
        """clip.exe 는 cp949 로 해석해 한글이 깨진다. UTF-8 → Set-Clipboard 를 쓴다."""
        src = read_app_source()
        self.assertIn("Set-Clipboard", src)
        self.assertIn("-Encoding UTF8", src)
        self.assertNotIn('["clip"]', src)

    def test_payload_is_utf16_null_terminated(self):
        self.assertEqual(app._clipboard_payload("원"), "원".encode("utf-16-le") + b"\x00\x00")
        self.assertEqual(app._clipboard_payload(""), b"\x00\x00")

    def test_empty_text_is_rejected(self):
        self.assertFalse(app.set_clipboard(""))
        self.assertFalse(app.set_clipboard(None))

    def test_api_copy_returns_set_clipboard_result(self):
        api = app.Api(object())
        original = app.set_clipboard
        app.set_clipboard = lambda text: text == SAMPLE
        try:
            self.assertTrue(api.copy(SAMPLE))
            self.assertFalse(api.copy("다른 값"))
        finally:
            app.set_clipboard = original

    def test_roundtrip_when_clipboard_is_available(self):
        """실제 클립보드에 넣고(한글·줄바꿈 포함) 그대로 읽어 오는지 확인한다."""
        if not app.set_clipboard(SAMPLE):
            self.skipTest("이 환경에서는 클립보드를 쓸 수 없습니다")
        self.assertEqual(_read_clipboard(), SAMPLE)


class _FakeFn:
    """ctypes 함수처럼 argtypes/restype 을 받아 주는 대역."""

    def __init__(self, name, impl):
        self.name = name
        self.impl = impl
        self.argtypes = None
        self.restype = None
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.impl(*args)


class _FakeLib:
    def __init__(self, impls):
        self._impls = impls
        self._fns = {}

    def __getattr__(self, name):
        if name.startswith("_") or name not in self._impls:
            raise AttributeError(name)
        if name not in self._fns:
            self._fns[name] = _FakeFn(name, self._impls[name])
        return self._fns[name]


class _FakeWin32:
    """user32/kernel32 를 흉내 내 Win32 클립보드 경로를 리눅스에서도 검사한다."""

    def __init__(self, open_after=1, set_ok=True):
        self.open_after = open_after
        self.set_ok = set_ok
        self.open_attempts = 0
        self.closed = 0
        self.freed = []
        self.set_calls = []
        self.buffer = None
        self.user32 = _FakeLib(
            {
                "OpenClipboard": self.open_clipboard,
                "EmptyClipboard": lambda *_a: 1,
                "CloseClipboard": self.close_clipboard,
                "SetClipboardData": self.set_clipboard_data,
            }
        )
        self.kernel32 = _FakeLib(
            {
                "GlobalAlloc": self.global_alloc,
                "GlobalLock": self.global_lock,
                "GlobalUnlock": lambda *_a: 1,
                "GlobalFree": self.global_free,
            }
        )

    # user32 ---------------------------------------------------------
    def open_clipboard(self, _hwnd):
        self.open_attempts += 1
        return 1 if self.open_attempts >= self.open_after else 0

    def close_clipboard(self):
        self.closed += 1
        return 1

    def set_clipboard_data(self, fmt, handle):
        self.set_calls.append((fmt, handle))
        return handle if self.set_ok else 0

    # kernel32 -------------------------------------------------------
    def global_alloc(self, flags, size):
        self.buffer = ctypes.create_string_buffer(size)
        self.flags = flags
        return ctypes.addressof(self.buffer)

    def global_lock(self, _handle):
        return ctypes.addressof(self.buffer)

    def global_free(self, handle):
        self.freed.append(handle)
        return 0


def _windll_factory(fake):
    def fake_windll(name, **_kwargs):
        return fake.user32 if name == "user32" else fake.kernel32

    return fake_windll


class TestWin32ClipboardPath(unittest.TestCase):
    """64비트 윈도우 클립보드 경로(ctypes)를 가짜 Win32 DLL 로 실제 실행해 본다."""

    def _run(self, fake, text):
        with mock.patch("ctypes.WinDLL", _windll_factory(fake), create=True):
            return app._set_clipboard_win32(text)

    def test_writes_utf16_and_keeps_handle(self):
        fake = _FakeWin32()
        self.assertTrue(self._run(fake, "원"))
        # CF_UNICODETEXT 로 UTF-16LE + 널 종료가 그대로 들어갔다.
        self.assertEqual(fake.flags, app.GMEM_MOVEABLE)
        self.assertEqual(fake.set_calls, [(app.CF_UNICODETEXT, ctypes.addressof(fake.buffer))])
        written = fake.buffer.raw[: len("원".encode("utf-16-le")) + 2]
        self.assertEqual(written, "원".encode("utf-16-le") + b"\x00\x00")
        # 성공하면 클립보드가 메모리를 소유하므로 해제하지 않고, 클립보드는 닫는다.
        self.assertEqual(fake.freed, [])
        self.assertEqual(fake.closed, 1)

    def test_retries_when_clipboard_is_busy(self):
        fake = _FakeWin32(open_after=2)
        self.assertTrue(self._run(fake, "정산 내역"))
        self.assertEqual(fake.open_attempts, 2)

    def test_gives_up_when_clipboard_stays_busy(self):
        fake = _FakeWin32(open_after=99)
        self.assertFalse(self._run(fake, "정산 내역"))
        self.assertEqual(fake.open_attempts, app.CLIPBOARD_OPEN_RETRIES)
        self.assertEqual(fake.closed, 0)

    def test_failed_set_frees_the_handle(self):
        fake = _FakeWin32(set_ok=False)
        self.assertFalse(self._run(fake, "정산 내역"))
        self.assertEqual(fake.freed, [ctypes.addressof(fake.buffer)])
        self.assertEqual(fake.closed, 1)

    def test_every_win32_function_gets_signatures(self):
        fake = _FakeWin32()
        self.assertTrue(self._run(fake, "정산 내역"))
        for fn in (
            fake.user32._fns["OpenClipboard"],
            fake.user32._fns["EmptyClipboard"],
            fake.user32._fns["SetClipboardData"],
            fake.user32._fns["CloseClipboard"],
            fake.kernel32._fns["GlobalAlloc"],
            fake.kernel32._fns["GlobalLock"],
            fake.kernel32._fns["GlobalUnlock"],
            fake.kernel32._fns["GlobalFree"],
        ):
            self.assertIsNotNone(fn.argtypes, f"{fn.name} argtypes")
            self.assertIsNotNone(fn.restype, f"{fn.name} restype")


class TestCopyButtonOrder(unittest.TestCase):
    """화면(JS)은 사용자 클릭 직후의 navigator.clipboard 를 먼저, 파이썬 브리지는 마지막에."""

    def test_js_order(self):
        html = read_web()
        first = html.index("await navigator.clipboard.writeText(text); done = true;")
        second = html.index("done = legacyCopy(text)")
        third = html.index("await api.copy(text)")
        self.assertLess(first, second)
        self.assertLess(second, third)

    def test_js_guards_empty_text(self):
        html = read_web()
        self.assertIn('if (!text.trim()) { showToast("복사할 내용이 없습니다"); return; }', html)

    def test_js_legacy_copy_selects_the_textarea(self):
        html = read_web()
        self.assertIn("function legacyCopy(text)", html)
        self.assertIn("ta.setSelectionRange(0, ta.value.length);", html)
        self.assertIn('document.execCommand("copy")', html)

    def test_copy_button_uses_receipt_text(self):
        html = read_web()
        self.assertIn('copyBtn.addEventListener("click", () => copyText(receiptText));', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
