"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import http.server
import importlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
SCRATCH = os.path.join(ROOT, ".cora_grader")
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


NF = (404, {"error": "not found"})


def h():
    return importlib.import_module("app").handle


@check
def list_and_create():
    s = {}
    expect(h()("GET", "/notes", b"", s), (200, []), "GET /notes empty")
    expect(h()("POST", "/notes", b'{"text": "a"}', s), (201, {"id": 1, "text": "a"}), "POST a")
    expect(h()("POST", "/notes", b'{"text": "b"}', s), (201, {"id": 2, "text": "b"}), "POST b")
    expect(h()("GET", "/notes", b"", s),
           (200, [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}]), "GET /notes")
    s2 = {5: {"id": 5, "text": "z"}}
    expect(h()("POST", "/notes", b'{"text": "c"}', s2)[1]["id"], 6, "id after 5")


@check
def get_one_and_missing():
    s = {1: {"id": 1, "text": "a"}}
    expect(h()("GET", "/notes/1", b"", s), (200, {"id": 1, "text": "a"}), "GET 1")
    expect(h()("GET", "/notes/9", b"", s), NF, "GET 9")
    expect(h()("GET", "/notes/x", b"", s), NF, "GET x")


@check
def validation():
    s = {}
    for body in (b"not json", b'{"text": ""}', b'{"text": 5}', b"[1]"):
        expect(h()("POST", "/notes", body, s), (400, {"error": "invalid note"}), f"POST {body!r}")
    expect(s, {}, "store after invalid posts")


@check
def delete_note():
    s = {1: {"id": 1, "text": "a"}}
    expect(h()("DELETE", "/notes/1", b"", s), (204, None), "DELETE 1")
    expect(h()("GET", "/notes/1", b"", s), NF, "GET after delete")
    expect(h()("DELETE", "/notes/1", b"", s), NF, "DELETE again")


@check
def routing():
    expect(h()("GET", "/other", b"", {}), NF, "GET /other")
    expect(h()("PUT", "/notes", b"", {}), (405, {"error": "method not allowed"}), "PUT /notes")


@check
def handler_class():
    app = importlib.import_module("app")
    assert issubclass(app.NotesHandler, http.server.BaseHTTPRequestHandler), "not a handler"
    for m in ("do_GET", "do_POST", "do_DELETE"):
        assert callable(getattr(app.NotesHandler, m, None)), f"missing {m}"
    assert callable(app.make_server), "missing make_server"


def main():
    results = []
    for fn in CHECKS:
        try:
            fn()
            results.append({"name": fn.__name__, "passed": True, "detail": ""})
        except AssertionError as e:
            results.append({"name": fn.__name__, "passed": False, "detail": str(e)[:300]})
        except Exception as e:  # noqa: BLE001
            results.append({"name": fn.__name__, "passed": False, "detail": type(e).__name__})
    print(json.dumps({"checks": results}, sort_keys=True))


if __name__ == "__main__":
    main()
