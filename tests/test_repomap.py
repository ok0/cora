import json
import os
import time
from pathlib import Path

from cora.core import repomap
from cora.core.repomap import CACHE_RELPATH, TRUNCATION_MARKER, RepoMap, python_symbols
from cora.core.shellguard import PathGuard, default_protected
from repo_fixture import PLANTED, SECRET, make_large_repo


def _guard(ws: Path) -> PathGuard:
    return PathGuard(ws, default_protected())


def test_map_excludes_credentials_and_protected(tmp_path: Path) -> None:
    ws = make_large_repo(tmp_path / "repo")
    cache = ws / ".cora" / CACHE_RELPATH
    RepoMap.build(ws, _guard(ws), max_files=10_000, cache_path=cache)
    assert cache.exists()

    rm = RepoMap.build(ws, _guard(ws), max_files=10_000)
    paths = {e.path for e in rm.entries}
    for p in PLANTED:
        assert p not in paths
    assert not any(p.startswith(".cora/") for p in paths)

    text = rm.render(10**7)
    assert SECRET not in text
    for line in text.splitlines():
        assert not line.startswith((".env", ".git/", "id_rsa", "deploy.key", "certs/server.pem"))


def test_render_deterministic_and_truncated(tmp_path: Path) -> None:
    ws = make_large_repo(tmp_path / "repo")
    rm1 = RepoMap.build(ws, _guard(ws), max_files=10_000, cache_path=None)
    rm2 = RepoMap.build(ws, _guard(ws), max_files=10_000, cache_path=None)
    assert rm1.render(4000) == rm2.render(4000)

    t = rm1.render(300)
    assert len(t) <= 300
    assert t.endswith(TRUNCATION_MARKER)

    for n in (1, 5, 25, 4000):
        assert len(rm1.render(n)) <= n


def test_python_symbols_top_level_only() -> None:
    src = b"import os\ndef a(): pass\nclass B:\n    def inner(self): pass\nasync def c(): pass\n"
    assert python_symbols(src) == ("a", "B", "c")


def test_unparseable_and_binary_are_path_and_size(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    files = {
        "broken.py": b"def (:\n",
        "blob.bin": bytes(range(256)),
        "nul.py": b"\x00\x01def x(): pass",
    }
    for name, data in files.items():
        (ws / name).write_bytes(data)

    rm = RepoMap.build(ws, _guard(ws), max_files=10_000)
    by_path = {e.path: e for e in rm.entries}
    rendered = rm.render(10**6).splitlines()
    for name, data in files.items():
        entry = by_path[name]
        assert entry.symbols == ()
        assert entry.size == len(data)
        assert f"{name} ({len(data)} B)" in rendered


def test_cache_reuse_and_invalidation(tmp_path: Path, monkeypatch) -> None:
    ws = make_large_repo(tmp_path / "repo", py_files=40, other_files=10)
    cp = ws / ".cora" / CACHE_RELPATH
    guard = _guard(ws)

    first = RepoMap.build(ws, guard, max_files=10_000, cache_path=cp)
    py_count = sum(1 for e in first.entries if e.path.endswith(".py"))
    assert first.parsed == py_count
    assert cp.exists()

    calls: list[bytes] = []
    original = repomap.python_symbols

    def counting(source: bytes) -> tuple[str, ...]:
        calls.append(source)
        return original(source)

    monkeypatch.setattr(repomap, "python_symbols", counting)

    second = RepoMap.build(ws, guard, max_files=10_000, cache_path=cp)
    assert second.parsed == 0
    assert second.entries == first.entries
    assert calls == []

    target = ws / "pkg" / "mod_005.py"
    target.write_text("class C5:\n    pass\n\n\ndef renamed_5():\n    return 5\n", encoding="utf-8")
    later = os.stat(target).st_mtime + 10
    os.utime(target, (later, later))
    third = RepoMap.build(ws, guard, max_files=10_000, cache_path=cp)
    assert third.parsed == 1
    entry = next(e for e in third.entries if e.path == "pkg/mod_005.py")
    assert entry.symbols == ("C5", "renamed_5")

    ws.joinpath("pkg", "mod_006.py").unlink()
    fourth = RepoMap.build(ws, guard, max_files=10_000, cache_path=cp)
    assert fourth.parsed == 0
    assert not any(e.path == "pkg/mod_006.py" for e in fourth.entries)
    data = json.loads(cp.read_text(encoding="utf-8"))
    assert "pkg/mod_006.py" not in data["files"]


def test_max_files_bound_and_speed(tmp_path: Path) -> None:
    ws = make_large_repo(tmp_path / "repo")
    cp = ws / ".cora" / CACHE_RELPATH

    start = time.perf_counter()
    full = RepoMap.build(ws, _guard(ws), max_files=500, cache_path=cp)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
    assert len(full.entries) <= 500

    a = RepoMap.build(ws, _guard(ws), max_files=50)
    b = RepoMap.build(ws, _guard(ws), max_files=50)
    assert len(a.entries) == 50
    assert a.capped is True
    assert a.entries == b.entries
    assert a.render(10**6).endswith(TRUNCATION_MARKER)


def test_build_no_network(tmp_path: Path, no_network: list[str]) -> None:
    ws = make_large_repo(tmp_path / "repo")
    rm = RepoMap.build(ws, _guard(ws), max_files=10_000)
    rm.render(4000)
    assert no_network == []
