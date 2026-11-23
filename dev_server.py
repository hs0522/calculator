import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import calculator  # noqa: E402
from version import APP_VERSION  # noqa: E402

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
REPO = "hs0522/calculator"
WINDOW_ACTIONS = {
    "/api/minimize",
    "/api/close",
    "/api/set_on_top",
    "/api/open_release",
    "/api/get_window_state",
    "/api/copy",
}


def presets_payload():
    return [
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
    ]


def handle_api(path, payload):
    try:
        if path == "/api/presets":
            return {"ok": True, "presets": presets_payload()}
        if path == "/api/version":
            return {"ok": True, "version": APP_VERSION, "repo": REPO}
        if path == "/api/check_update":
            forced = os.environ.get("PILATES_PREVIEW_UPDATE") == "1"
            return {
                "ok": True,
                "current": APP_VERSION,
                "latest": "1.0.1" if forced else APP_VERSION,
                "available": forced,
                "url": f"https://github.com/{REPO}/releases/latest",
            }
        if path in WINDOW_ACTIONS:
            return {"ok": True, "always_on_top": True}
        if path == "/api/date_calc":
            return calculator.build_expiry_result(
                payload.get("start"),
                payload.get("value"),
                payload.get("unit", "months"),
                payload.get("label", ""),
            )
        if path == "/api/refund_calc":
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
    return {"ok": False, "error": "알 수 없는 요청입니다."}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, fmt, *args):  # 조용히
        pass

    def _json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload = {}
        self._json(handle_api(self.path, payload))

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._json(handle_api(self.path.split("?")[0], {}))
            return
        if self.path in ("/", ""):
            self.path = "/index.html"
        super().do_GET()


def main():
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"preview: http://127.0.0.1:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
