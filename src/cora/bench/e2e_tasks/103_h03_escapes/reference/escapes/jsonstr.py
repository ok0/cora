_SHORT = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}

_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

_HEX = "0123456789abcdefABCDEF"


def encode(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch in _SHORT:
            out.append(_SHORT[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _hex4(body: str, i: int) -> int:
    chunk = body[i : i + 4]
    if len(chunk) != 4 or any(c not in _HEX for c in chunk):
        raise ValueError("bad \\u escape")
    return int(chunk, 16)


def decode(lit: str) -> str:
    if len(lit) < 2 or lit[0] != '"' or lit[-1] != '"':
        raise ValueError("not a JSON string literal")
    body = lit[1:-1]
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(body):
            raise ValueError("dangling backslash")
        esc = body[i + 1]
        if esc == "u":
            code = _hex4(body, i + 2)
            i += 6
            if 0xD800 <= code <= 0xDBFF:
                if body[i : i + 2] != "\\u":
                    raise ValueError("lone surrogate")
                low = _hex4(body, i + 2)
                if not 0xDC00 <= low <= 0xDFFF:
                    raise ValueError("lone surrogate")
                code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                i += 6
            elif 0xDC00 <= code <= 0xDFFF:
                raise ValueError("lone surrogate")
            out.append(chr(code))
            continue
        if esc not in _ESCAPES:
            raise ValueError(f"unknown escape: \\{esc}")
        out.append(_ESCAPES[esc])
        i += 2
    return "".join(out)
