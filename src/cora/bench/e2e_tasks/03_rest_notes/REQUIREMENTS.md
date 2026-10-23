# Notes REST handler

Implement a tiny JSON REST API for notes in `app.py` using only the standard library
(`http.server`, `json`). Keep the routing logic in a pure function so it can be tested
without opening a socket.

1. `handle(method: str, path: str, body: bytes, store: dict) -> tuple[int, object]` returns
   `(status, payload)`. `store` maps note id (int) to the note dict and is modified in place.
   Notes are `{"id": <int>, "text": <str>}`.
   - GET on the collection path `/notes` -> 200 and the list of all notes sorted by id.
   - POST on `/notes` with a JSON object body `{"text": <non-empty string>}` -> 201 and the new
     note. Its id is 1 + the largest id in `store` (1 when empty). Anything else (invalid JSON,
     not an object, missing/empty/non-string text) -> 400 and `{"error": "invalid note"}`.
   - GET on `/notes/<id>` -> 200 and the note; DELETE on `/notes/<id>` -> 204 and payload
     `None`. A missing note or a non-integer id -> 404 and `{"error": "not found"}`.
   - Any other path -> 404 and `{"error": "not found"}`. A known path with an unsupported
     method (for example PUT on `/notes`) -> 405 and `{"error": "method not allowed"}`.
2. `class NotesHandler(http.server.BaseHTTPRequestHandler)` with `do_GET`, `do_POST`, `do_PUT`
   and `do_DELETE` that read the request body (Content-Length), call `handle` with the
   module-level `STORE` dict and write the payload as JSON with `Content-Type:
   application/json` (no body for 204).
3. `make_server(port: int = 0) -> http.server.HTTPServer` bound to 127.0.0.1 (port 0 picks a
   free port).
