from csvreport import column_stats, parse_csv


def test_parse_simple():
    assert parse_csv("a,b\n1,2\n") == [["a", "b"], ["1", "2"]]


def test_parse_quoted():
    assert parse_csv('name,note\n"x, y","say ""hi"""\n') == [["name", "note"], ["x, y", 'say "hi"']]


def test_stats_basic():
    rows = [["id", "v"], ["1", "1"], ["2", "3"], ["3", "5"]]
    assert column_stats(rows, "v") == {"count": 3, "min": 1.0, "max": 5.0, "mean": 3.0}
