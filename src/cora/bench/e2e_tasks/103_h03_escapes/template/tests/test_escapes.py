from escapes.jsonstr import encode
from escapes.shell import quote
from escapes.winpath import to_posix


def test_shell_quote():
    assert quote("") == "''"
    assert quote("abc-1.txt") == "abc-1.txt"
    assert quote("it's") == "'it'\"'\"'s'"


def test_json_encode_basic():
    assert encode('a"b\\c\n') == '"a\\"b\\\\c\\n"'


def test_winpath():
    assert to_posix("C:\\Users\\a b\\x.txt") == "/c/Users/a b/x.txt"
    assert to_posix("\\\\server\\share\\f.txt") == "//server/share/f.txt"
