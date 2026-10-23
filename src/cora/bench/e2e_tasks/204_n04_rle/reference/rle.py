DIGITS = "0123456789"


def encode(s: str) -> str:
    if any(c in DIGITS for c in s):
        raise ValueError("digits not allowed")
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(f"{j - i}{s[i]}")
        i = j
    return "".join(out)


def decode(s: str) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "0" or s[i] not in DIGITS:
            raise ValueError("bad input")
        j = i
        while j < n and s[j] in DIGITS:
            j += 1
        if j >= n:
            raise ValueError("bad input")
        out.append(s[j] * int(s[i:j]))
        i = j + 1
    return "".join(out)
