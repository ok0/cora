import re

_SAFE = re.compile(r"[A-Za-z0-9_@%+=:,./-]+")


def quote(arg: str) -> str:
    if arg and _SAFE.fullmatch(arg):
        return arg
    return "'" + arg.replace("'", "'\"'\"'") + "'"
