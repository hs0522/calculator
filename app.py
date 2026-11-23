"""필라테스 만료일·환불 계산기 - Windows 데스크톱 앱 (pywebview).

실행:
    python app.py            # 창 열기
    python app.py --selftest # GUI 없이 코어 동작만 확인 (패키징 검증용)
"""

from __future__ import annotations

import os
import sys

import calculator

APP_NAME = "필라테스 만료일 · 환불 계산기"
WINDOW_TITLE = "필라테스 계산기"


def resource_path(*parts: str) -> str:
    """PyInstaller(_MEIPASS)와 소스 실행 모두에서 동작하는 경로."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


# ---------------------------------------------------------------------------
# 클립보드 (pywebview 창에서 JS 복사 API가 막힐 때를 대비)
# ---------------------------------------------------------------------------


def set_clipboard(text: str) -> bool:
    text = text or ""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalAlloc.restype = ctypes.c_void_p
            kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            user32.SetClipboardData.restype = ctypes.c_void_p
            user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]

            data = text.encode("utf-16-le") + b"\x00\x00"
            if not user32.OpenClipboard(None):
                raise OSError("OpenClipboard 실패")
            try:
                user32.EmptyClipboard()
                handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
                if not handle:
                    raise OSError("GlobalAlloc 실패")
                ptr = kernel32.GlobalLock(handle)
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(handle)
                if not user32.SetClipboardData(13, handle):  # CF_UNICODETEXT
                    raise OSError("SetClipboardData 실패")
            finally:
                user32.CloseClipboard()
            return True
        except Exception:
            pass

    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JS <-> Python 브리지
# ---------------------------------------------------------------------------


class Api:
    """web/index.html 이 window.pywebview.api 로 호출하는 함수들."""

    def presets(self):
        return {
            "ok": True,
            "presets": [
                {
                    "id": p.id,
                    "kind": p.kind,
                    "kind_label": p.kind_label,
                    "sessions": p.sessions,
                    "period_value": p.period_value,
                    "period_unit": p.period_unit,
                    "period_label": p.period_label,
                    "price": p.price,
                    "per_session": p.per_session,
                    "label": p.label,
                }
                for p in calculator.PRESETS
            ],
        }

    def date_calc(self, payload=None):
        payload = payload or {}
        try:
            return calculator.build_expiry_result(
                payload.get("start"),
                payload.get("value"),
                payload.get("unit", "months"),
                payload.get("label", ""),
            )
        except calculator.CalcError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"계산 중 오류가 발생했습니다. ({exc})"}

    def refund_calc(self, payload=None):
        payload = payload or {}
        try:
            return calculator.build_refund_result(
                payload.get("paid"),
                payload.get("used"),
                payload.get("per_session"),
                payload.get("sessions"),
                payload.get("label", ""),
            )
        except calculator.CalcError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"계산 중 오류가 발생했습니다. ({exc})"}

    def copy(self, text):
        return set_clipboard(str(text or ""))


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def selftest(strict: bool = False) -> int:
    from datetime import date

    checks = {
        "만료일 2개월": calculator.calculate_expiry(date(2026, 11, 23), 2, "months") == date(2027, 1, 22),
        "만료일 10주": calculator.calculate_expiry(date(2026, 11, 23), 10, "weeks") == date(2027, 1, 31),
        "환불 12회 5회 사용": calculator.calculate_refund(264_000, 5, 22_000, 12).refund == 127_600,
        "web/index.html": os.path.exists(resource_path("web", "index.html")),
    }
    ok = all(checks.values())

    webview_ok = False
    webview_note = ""
    try:
        import webview  # noqa: F401

        webview_ok = True
        webview_note = getattr(webview, "__version__", "unknown")
    except Exception as exc:  # noqa: BLE001
        webview_note = f"{type(exc).__name__}: {exc}"

    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")
    print(f"  [{'OK' if webview_ok else 'FAIL'}] pywebview {webview_note}")
    print("selftest:", "OK" if ok and (webview_ok or not strict) else "FAIL")
    return 0 if ok and (webview_ok or not strict) else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest(strict="--strict" in sys.argv)

    import webview

    window = webview.create_window(
        WINDOW_TITLE,
        resource_path("web", "index.html"),
        js_api=Api(),
        width=1060,
        height=720,
        min_size=(820, 600),
        text_select=True,
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
