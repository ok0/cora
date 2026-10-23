from pathlib import Path

SECRET = "sk-planted-SECRET-7f3a9c"
PLANTED = (".env", ".env.local", "deploy.key", "id_rsa", "certs/server.pem", ".git/config")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_large_repo(root: Path, *, py_files: int = 300, other_files: int = 150) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "answer.py", "def find_answer():\n    return 42\n")
    _write(root / "README.md", "# Sample repo\n\nA few lines of readme.\n\nEnd.\n")
    _write(
        root / "pkg" / "big_a.py",
        "".join(f"def f_{i}(x):  # padding padding padding\n" for i in range(90)),
    )
    for i in range(py_files - 2):
        _write(
            root / "pkg" / f"mod_{i:03d}.py",
            f"class C{i}:\n    pass\n\n\ndef fn_{i}():\n    return {i}\n\nX_{i} = {i}\n",
        )
    for i in range(other_files):
        _write(root / "data" / f"file_{i:03d}.txt", f"line one {i}\nline two\nline three\n")
    for rel in PLANTED:
        _write(root / rel, f"TOKEN={SECRET}\n")
    return root
