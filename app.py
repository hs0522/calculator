"""필라테스 계산기 - 경량 플로팅 위젯 (pywebview).

실행:
    python app.py                 # 위젯 창 열기
    python app.py --selftest      # GUI 없이 코어 동작 확인
    python app.py --selftest --strict   # pywebview 로딩까지 확인 (패키징 검증용)

창 위치·항상 위 고정 상태는 %APPDATA%/PilatesCalc/state.json 에 저장한다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import webbrowser

import calculator
from version import APP_VERSION


def _ensure_std_streams() -> None:
    """--windowed(PyInstaller) 빌드의 표준 출력을 안전하게 만든다.

    창 모드에서 sys.stdout/stderr 가 None 이면 print 가 예외로 죽고, 리다이렉트된 파일은
    로케일 인코딩(cp1252 등)이라 한글 출력에서 UnicodeEncodeError 가 난다. 어느 경우든
    그 예외가 창 모드 오류 대화상자로 떠서 자동 검증이 멈춘다. UTF-8 로 맞춰 둔다.
    """
    for name, fd in (("stdout", 1), ("stderr", 2)):
        stream = getattr(sys, name)
        if stream is None:
            try:
                stream = open(fd, "w", encoding="utf-8", errors="replace", closefd=False)
            except OSError:
                stream = open(os.devnull, "w", encoding="utf-8")
        else:
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):
                try:
                    stream = open(fd, "w", encoding="utf-8", errors="replace", closefd=False)
                except OSError:
                    pass
        setattr(sys, name, stream)


def _say(text: str) -> None:
    """출력 실패가 검증 자체를 막지 않게 한다."""
    try:
        print(text)
    except Exception:  # noqa: BLE001
        pass


_ensure_std_streams()

WINDOW_TITLE = "필라테스 계산기"
# 윈도우 WebView2 는 기본 폰트(Malgun Gothic)·스크롤바·DPI 차이로 같은 내용이 10~15px 더 높다.
# 336×456 에서는 오른쪽 세로 스크롤바가 생겨 342×478 로 여유를 둔다.
DEFAULT_SIZE = (342, 478)
MIN_SIZE = (316, 460)
REPO = "hs0522/calculator"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"


def resource_path(*parts: str) -> str:
    """PyInstaller(_MEIPASS)와 소스 실행 모두에서 동작하는 경로."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


# ---------------------------------------------------------------------------
# 상태 저장 (%APPDATA%/PilatesCalc/state.json)
# ---------------------------------------------------------------------------


def state_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~/.config")
    path = os.path.join(base, "PilatesCalc")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def state_path() -> str:
    return os.path.join(state_dir(), "state.json")


def load_state() -> dict:
    try:
        with open(state_path(), encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(**values) -> dict:
    state = load_state()
    state.update(values)
    try:
        tmp = state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(state, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, state_path())
    except Exception:
        pass
    return state


# ---------------------------------------------------------------------------
# 클립보드
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
# 업데이트 확인
# ---------------------------------------------------------------------------


def _version_tuple(text: str) -> tuple:
    parts = []
    for chunk in str(text).lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    a, b = _version_tuple(latest), _version_tuple(current)
    length = max(len(a), len(b))
    a += (0,) * (length - len(a))
    b += (0,) * (length - len(b))
    return a > b


def github_token() -> str:
    """비공개 저장소면 토큰이 필요하다. config.json 의 github_token 을 쓴다."""
    token = os.getenv("PILATESCALC_GH_TOKEN", "")
    if token:
        return token
    try:
        with open(os.path.join(state_dir(), "config.json"), encoding="utf-8") as fp:
            return str(json.load(fp).get("github_token", "") or "")
    except Exception:
        return ""


def check_update(timeout: float = 5.0) -> dict:
    """최신 릴리즈를 확인한다. 실패해도 앱 동작에는 영향이 없다."""
    request = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PilatesCalc"},
    )
    token = github_token()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "current": APP_VERSION, "available": False, "error": str(exc)}

    latest = str(data.get("tag_name") or "").lstrip("vV")
    available = bool(latest) and is_newer(latest, APP_VERSION)
    return {
        "ok": True,
        "current": APP_VERSION,
        "latest": latest,
        "available": available,
        "url": data.get("html_url") or RELEASES_URL,
    }


# ---------------------------------------------------------------------------
# 위젯 / JS 브리지
# ---------------------------------------------------------------------------


class Widget:
    def __init__(self) -> None:
        self.window = None
        state = load_state()
        self.always_on_top = bool(state.get("always_on_top", True))
        self.x = state.get("x")
        self.y = state.get("y")

    # 창 위치 기억 -----------------------------------------------------
    def on_moved(self, *args) -> None:
        """창을 옴기면 위치를 저장한다."""
        if len(args) >= 2 and all(isinstance(v, int) for v in args[:2]):
            self.x, self.y = int(args[0]), int(args[1])
            save_state(x=self.x, y=self.y)

    def on_closing(self, *_args) -> None:
        """닫기 직전 위치를 한 번 더 저장한다."""
        window = self.window
        if window is None:
            return
        try:
            x, y = window.x, window.y
        except Exception:
            return
        if isinstance(x, int) and isinstance(y, int):
            self.x, self.y = x, y
            save_state(x=x, y=y)

    def apply_on_top(self, value: bool) -> bool:
        self.always_on_top = bool(value)
        save_state(always_on_top=self.always_on_top)
        if self.window is not None:
            try:
                self.window.on_top = self.always_on_top
            except Exception:
                pass
        return self.always_on_top

    def create_window(self):
        import webview

        kwargs = dict(
            js_api=Api(self),
            width=DEFAULT_SIZE[0],
            height=DEFAULT_SIZE[1],
            min_size=MIN_SIZE,
            frameless=True,
            easy_drag=False,
            resizable=True,
            text_select=True,
            on_top=self.always_on_top,
        )
        if isinstance(self.x, int) and isinstance(self.y, int):
            kwargs.update(x=self.x, y=self.y)

        self.window = webview.create_window(
            WINDOW_TITLE, resource_path("web", "index.html"), **kwargs
        )

        moved = getattr(self.window.events, "moved", None)
        if moved is not None:
            try:
                moved += self.on_moved
            except Exception:
                pass
        closing = getattr(self.window.events, "closing", None)
        if closing is not None:
            try:
                closing += self.on_closing
            except Exception:
                pass
        return self.window

    def run(self) -> None:
        import webview

        self.create_window()
        webview.start(lambda: self.apply_on_top(self.always_on_top))


class Api:
    """web/index.html 이 window.pywebview.api 로 호출한다."""

    def __init__(self, widget: Widget) -> None:
        self.widget = widget

    # 창 제어 ----------------------------------------------------------
    def version(self):
        return {"version": APP_VERSION, "repo": REPO}

    def minimize(self):
        try:
            self.widget.window.minimize()
        except Exception:
            pass
        return True

    def close(self):
        try:
            self.widget.window.destroy()
        except Exception:
            pass
        return True

    def set_on_top(self, value=True):
        return self.widget.apply_on_top(bool(value))

    def get_window_state(self):
        return {"always_on_top": self.widget.always_on_top}

    def check_update(self):
        return check_update()

    def open_release(self, url=""):
        target = url if isinstance(url, str) and url.startswith("https://") else RELEASES_URL
        try:
            webbrowser.open(target)
        except Exception:
            return False
        return True

    # 계산 --------------------------------------------------------------
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
        "버전 비교": is_newer("1.0.1", "1.0.0") and not is_newer("1.0.0", "1.0.0"),
        # index.html 이 window.pywebview.api 로 부르는 이름과 Api 메서드가 모두 맞는지 확인한다.
        "JS 브리지 메서드": all(
            callable(getattr(Api, name, None))
            for name in (
                "presets", "date_calc", "refund_calc", "copy", "get_window_state",
                "set_on_top", "minimize", "close", "check_update", "open_release", "version",
            )
        ),
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
        _say(f"  [{'OK' if passed else 'FAIL'}] {name}")
    _say(f"  [{'OK' if webview_ok else 'FAIL'}] pywebview {webview_note}")
    _say(f"  version: {APP_VERSION} | state: {state_path()}")
    _say("selftest: " + ("OK" if ok and (webview_ok or not strict) else "FAIL"))
    return 0 if ok and (webview_ok or not strict) else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest(strict="--strict" in sys.argv)
    Widget().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
