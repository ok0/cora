from dotenv_lite import parse


def test_basic_pairs():
    assert parse("NAME=ada\nPORT=8080\n") == {"NAME": "ada", "PORT": "8080"}


def test_comments_skipped():
    assert parse("# top\n\nA=1\n# mid\nB=2\n") == {"A": "1", "B": "2"}
