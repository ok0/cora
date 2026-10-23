import re

_DRIVE = re.compile(r"([A-Za-z]):(?=/|$)")


def to_posix(path: str) -> str:
    p = path.replace("\\", "/")
    head = ""
    if p.startswith("//"):
        head = "//"
        p = p[2:]
    else:
        m = _DRIVE.match(p)
        if m:
            head = "/" + m.group(1).lower()
            p = p[2:]
    while "//" in p:
        p = p.replace("//", "/")
    if p.endswith("/"):
        p = p[:-1]
    return head + p
