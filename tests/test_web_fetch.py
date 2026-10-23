from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from cora.core.config import ToolSettings
from cora.core.tools import ApprovalPolicy, ToolContext, ToolRegistry, Workspace, default_tools, web
from cora.core.tools.web import blocked_ip_reason

reg = ToolRegistry(default_tools())

DEFAULT_DNS = {
    "example.com": ["93.184.216.34"],
    "public.test": ["93.184.216.35"],
    "internal.test": ["10.1.2.3"],
}


async def _real_dns_forbidden(host: str, port: int) -> list[str]:
    raise AssertionError("real DNS used")


@pytest.fixture(autouse=True)
def no_real_dns(monkeypatch):
    monkeypatch.setattr(web, "system_resolve", _real_dns_forbidden)


class Server:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], Callable[[httpx.Request], Any]] = {}

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        route = self.routes.get((request.headers["host"], request.url.path))
        if route is None:
            return httpx.Response(404, text="not found")
        result = route(request)
        if inspect.isawaitable(result):
            result = await result
        return result


@pytest.fixture
def server() -> Server:
    return Server()


def fake_resolver(table: dict[str, list[str]]):
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such host")
        return table[host]

    return resolve


def mk_ctx(tmp_path, server, policy=None, dns=None, **limits) -> ToolContext:
    return ToolContext(
        Workspace(tmp_path),
        policy or ApprovalPolicy("auto"),
        limits=ToolSettings(**limits),
        http_transport=httpx.MockTransport(server.handler),
        resolver=fake_resolver(dns or DEFAULT_DNS),
    )


def _exec(ctx, args, name="web_fetch"):
    return asyncio.run(reg.execute(name, args, ctx))


def _html(body: str) -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "text/html; charset=utf-8"}, content=body.encode()
    )


def test_html_to_text_after_approval(tmp_path, server):
    server.routes[("example.com", "/")] = lambda r: _html(
        "<html><head><title>T</title></head><body>"
        "<script>evil()</script><style>p{color:red}</style>"
        "<p>Hello <b>world</b></p><p>Bye</p></body></html>"
    )
    reqs = []
    policy = ApprovalPolicy("ask", review=lambda r: reqs.append(r) or "yes")
    ctx = mk_ctx(tmp_path, server, policy=policy)
    res = _exec(ctx, {"url": "https://example.com/"})
    assert res.ok, res.output
    assert "Hello world" in res.output
    assert "Bye" in res.output
    assert "untrusted" in res.output
    assert "<p>" not in res.output
    assert "evil()" not in res.output
    assert reqs[0].detail == "GET https://example.com/"
    assert server.calls[0].url.host == "93.184.216.34"
    assert server.calls[0].headers["host"] == "example.com"
    assert server.calls[0].extensions["sni_hostname"] == "example.com"


def test_json_and_text_raw(tmp_path, server):
    server.routes[("example.com", "/data.json")] = lambda r: httpx.Response(
        200, headers={"content-type": "application/json"}, content=b'{"a": 1}'
    )
    server.routes[("example.com", "/plain")] = lambda r: httpx.Response(
        200, headers={"content-type": "text/plain"}, content=b"<b>raw</b>"
    )
    ctx = mk_ctx(tmp_path, server)
    assert '{"a": 1}' in _exec(ctx, {"url": "https://example.com/data.json"}).output
    assert "<b>raw</b>" in _exec(ctx, {"url": "https://example.com/plain"}).output


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/"]
)
def test_non_http_schemes_rejected(tmp_path, server, url):
    reviewed = []
    policy = ApprovalPolicy("ask", review=lambda r: reviewed.append(r) or "yes")
    ctx = mk_ctx(tmp_path, server, policy=policy)
    res = _exec(ctx, {"url": url})
    assert res.ok is False
    assert "only http and https" in res.output
    assert server.calls == []
    assert reviewed == []


def test_binary_rejected(tmp_path, server):
    server.routes[("example.com", "/img")] = lambda r: httpx.Response(
        200, headers={"content-type": "image/png"}, content=b"\x89PNG"
    )
    server.routes[("example.com", "/blob")] = lambda r: httpx.Response(
        200, content=b"\x00\x01abc"
    )
    ctx = mk_ctx(tmp_path, server)
    res = _exec(ctx, {"url": "https://example.com/img"})
    assert res.ok is False
    assert "unsupported content-type" in res.output
    res = _exec(ctx, {"url": "https://example.com/blob"})
    assert res.ok is False
    assert "binary" in res.output


def test_deny_sends_no_request(tmp_path, server):
    ctx = mk_ctx(tmp_path, server, policy=ApprovalPolicy("deny"))
    res = _exec(ctx, {"url": "https://example.com/"})
    assert res.ok is False
    assert "denied by user" in res.output
    assert server.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://sub.localhost/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.0.0.1]/",
        "http://0.0.0.0/",
    ],
)
def test_blocked_literal_addresses(tmp_path, server, url):
    ctx = mk_ctx(tmp_path, server)
    res = _exec(ctx, {"url": url})
    assert res.ok is False
    assert "blocked" in res.output
    assert server.calls == []


@pytest.mark.parametrize(
    "dns",
    [
        {"h.test": ["10.1.2.3"]},
        {"h.test": ["93.184.216.34", "127.0.0.1"]},
        {"h.test": ["::1"]},
        {"h.test": ["::ffff:192.168.0.1"]},
        {"h.test": ["169.254.169.254"]},
        {"h.test": ["64:ff9b::a00:1"]},
    ],
)
def test_blocked_resolved_hosts(tmp_path, server, dns):
    ctx = mk_ctx(tmp_path, server, dns=dns)
    res = _exec(ctx, {"url": "http://h.test/"})
    assert res.ok is False
    assert "blocked" in res.output
    assert server.calls == []


@pytest.mark.parametrize(
    "location",
    ["http://127.0.0.1/admin", "http://internal.test/", "file:///etc/passwd"],
)
def test_blocked_redirect_targets(tmp_path, server, location):
    server.routes[("public.test", "/")] = lambda r: httpx.Response(
        302, headers={"location": location}
    )
    ctx = mk_ctx(tmp_path, server)
    res = _exec(ctx, {"url": "http://public.test/"})
    assert res.ok is False
    assert "blocked" in res.output or "disallowed" in res.output
    assert len(server.calls) == 1


def test_redirect_followed_and_capped(tmp_path, server):
    server.routes[("example.com", "/a")] = lambda r: httpx.Response(
        302, headers={"location": "/b"}
    )
    server.routes[("example.com", "/b")] = lambda r: httpx.Response(
        200, headers={"content-type": "text/plain"}, content=b"final"
    )
    ctx = mk_ctx(tmp_path, server)
    res = _exec(ctx, {"url": "https://example.com/a"})
    assert res.ok, res.output
    assert "final" in res.output
    assert "URL: https://example.com/b" in res.output

    server.routes[("example.com", "/loop")] = lambda r: httpx.Response(
        302, headers={"location": "/loop"}
    )
    server.calls.clear()
    capped = mk_ctx(tmp_path, server, web_max_redirects=3)
    res = _exec(capped, {"url": "https://example.com/loop"})
    assert res.ok is False
    assert "too many redirects" in res.output
    assert len(server.calls) == 4


def test_body_cap_stops_download(tmp_path, server):
    counter = {"n": 0}

    async def body():
        for _ in range(1000):
            counter["n"] += 1
            yield b"x" * 1000

    server.routes[("example.com", "/big")] = lambda r: httpx.Response(
        200, headers={"content-type": "text/plain"}, content=body()
    )
    ctx = mk_ctx(tmp_path, server, web_max_download_bytes=5000)
    res = _exec(ctx, {"url": "https://example.com/big"})
    assert "[truncated: download limit 5000 bytes]" in res.output
    assert counter["n"] < 1000


def test_output_cap(tmp_path, server):
    server.routes[("example.com", "/long")] = lambda r: httpx.Response(
        200, headers={"content-type": "text/plain"}, content=("x" * 10000).encode()
    )
    ctx = mk_ctx(tmp_path, server, web_max_output_chars=500)
    res = _exec(ctx, {"url": "https://example.com/long"})
    assert "[truncated: output limit 500 chars]" in res.output
    assert len(res.output) <= 1000


def test_timeout(tmp_path, server):
    async def slow(request):
        await asyncio.sleep(5)
        return httpx.Response(200, content=b"late")

    server.routes[("example.com", "/slow")] = slow
    ctx = mk_ctx(tmp_path, server, web_timeout_s=0.2)
    started = time.monotonic()
    res = _exec(ctx, {"url": "https://example.com/slow"})
    assert res.ok is False
    assert "timed out" in res.output
    assert time.monotonic() - started < 3


@pytest.mark.parametrize(
    "addr",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "::127.0.0.1",
        "64:ff9b::7f00:1",
        "224.0.0.1",
        "ff0e::1",
        "100.64.0.1",
        "fd00:ec2::254",
    ],
)
def test_blocked_ip_reason_unit(addr):
    assert blocked_ip_reason(addr) is not None


@pytest.mark.parametrize("addr", ["93.184.216.34", "2606:4700:4700::1111"])
def test_public_ip_reason_unit(addr):
    assert blocked_ip_reason(addr) is None


def test_extra_args_rejected(tmp_path, server):
    ctx = mk_ctx(tmp_path, server)
    res = _exec(ctx, {"url": "https://example.com/", "headers": {"a": "b"}})
    assert res.ok is False
    assert "unsupported argument" in res.output
    assert server.calls == []
