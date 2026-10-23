"""Notes REST handler - reference solution (tests only)."""

import http.server
import json

STORE: dict[int, dict] = {}
NOT_FOUND = (404, {"error": "not found"})


def _create(body: bytes, store: dict) -> tuple[int, object]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        data = None
    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str) or not text:
        return 400, {"error": "invalid note"}
    note_id = max(store, default=0) + 1
    store[note_id] = {"id": note_id, "text": text}
    return 201, store[note_id]


def handle(method: str, path: str, body: bytes, store: dict) -> tuple[int, object]:
    if path == "/notes":
        if method == "GET":
            return 200, [store[k] for k in sorted(store)]
        if method == "POST":
            return _create(body, store)
        return 405, {"error": "method not allowed"}
    if path.startswith("/notes/"):
        raw = path[len("/notes/"):]
        if method not in ("GET", "DELETE"):
            return 405, {"error": "method not allowed"}
        if not raw.isdigit() or int(raw) not in store:
            return NOT_FOUND
        note_id = int(raw)
        if method == "DELETE":
            del store[note_id]
            return 204, None
        return 200, store[note_id]
    return NOT_FOUND


class NotesHandler(http.server.BaseHTTPRequestHandler):
    def _dispatch(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        status, payload = handle(self.command, self.path, body, STORE)
        self.send_response(status)
        if status == 204:
            self.end_headers()
            return
        data = json.dumps(payload).encode("utf-8")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = _dispatch


def make_server(port: int = 0) -> http.server.HTTPServer:
    return http.server.HTTPServer(("127.0.0.1", port), NotesHandler)
