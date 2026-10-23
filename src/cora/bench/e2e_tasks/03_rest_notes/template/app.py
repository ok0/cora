"""Notes REST handler - see REQUIREMENTS.md."""

import http.server

STORE: dict[int, dict] = {}


def handle(method: str, path: str, body: bytes, store: dict) -> tuple[int, object]:
    raise NotImplementedError


class NotesHandler(http.server.BaseHTTPRequestHandler):
    pass


def make_server(port: int = 0) -> http.server.HTTPServer:
    raise NotImplementedError
