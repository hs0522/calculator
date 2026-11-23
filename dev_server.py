import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import calculator  # noqa: E402

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


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

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload = {}
        result = handle_api(self.path, payload)
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/presets"):
            body = json.dumps(handle_api("/api/presets", {}), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
