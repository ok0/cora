from pathlib import Path

import pytest

import m19_oracle as O
from cora.bench.stats import wilson_interval

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/m19/m19d-oracle.md"


def test_choose_higher_rate():
    assert O.choose((1, 3, 0.03), (2, 3, 0.09)) == ("strong", "higher rate")
    assert O.choose((2, 3, 0.03), (1, 3, 0.09)) == ("cheap", "higher rate")


def test_choose_tie_goes_to_cheaper():
    assert O.choose((1, 3, 0.06), (2, 6, 0.30)) == ("cheap", "tie, cheaper")
    assert O.choose((0, 3, 0.30), (0, 3, 0.03)) == ("strong", "tie, cheaper")
    assert O.choose((1, 3, 0.09), (1, 3, 0.09)) == ("cheap", "tie, cheaper")


def test_choose_missing():
    assert O.choose(None, (1, 3, 0.1)) == ("strong", "only data")
    assert O.choose((1, 3, 0.1), None) == ("cheap", "only data")
    assert O.choose(None, None) == ("none", "no data")


def test_best_cheap_tie_by_cost():
    assert O.best_cheap({"m1": (1, 3, 0.30), "m2": (1, 3, 0.06), "m3": (0, 3, 0.01)}) == (
        "m2",
        (1, 3, 0.06),
    )
    assert O.best_cheap({}) is None


def test_oracle_missing_named():
    cheap_by = {"t1": {"c": (2, 3, 0.3)}, "t2": {"c": (0, 3, 0.3)}}
    strong_by = {"t1": {"s": (1, 3, 0.6)}}
    res = O.oracle(cheap_by, strong_by, ("t1", "t2", "t3"))
    assert [p["choice"] for p in res["per_task"]] == ["cheap", "cheap", "none"]
    assert [p["reason"] for p in res["per_task"]] == ["higher rate", "only data", "no data"]
    assert res["missing"] == ["t3"]
    assert res["chosen"] == {"t1": (2, 3, 0.3), "t2": (0, 3, 0.3)}


def test_summarize_wilson_spd_missing():
    s = O.summarize("x", "cfg", {"t1": (2, 3, 0.5), "t2": (1, 3, 0.5)}, ("t1", "t2", "t3"))
    assert s["k"] == 3
    assert s["n"] == 6
    assert s["cost"] == pytest.approx(1.0)
    assert s["spd"] == pytest.approx(3.0)
    assert s["wilson"] == wilson_interval(3, 6)
    assert s["missing"] == ["t3"]

    empty = O.summarize("x", "cfg", {}, ("t1",))
    assert empty["n"] == 0
    assert empty["wilson"] is None
    assert empty["ratio"] is None
    assert empty["spd"] is None


def test_strong_arm_must_have_one_model():
    with pytest.raises(O.PanelError):
        O.oracle({}, {"t1": {"s1": (1, 3, 0.1), "s2": (1, 3, 0.1)}}, ("t1",))


def test_main_regenerates_fixture(tmp_path, no_network, monkeypatch):
    monkeypatch.chdir(ROOT)
    for k in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    out = tmp_path / "o.md"
    assert O.main(["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == FIXTURE.read_text(encoding="utf-8")
    assert no_network == []


def test_fixture_content():
    text = FIXTURE.read_text(encoding="utf-8")
    for needle in (
        "## Oracle rule",
        "## Caveats",
        "upper bound",
        "post-hoc",
        "## View: billed",
        "## View: registered",
    ):
        assert needle in text
    for t in O.TASKS:
        assert text.count(f"| {t} |") >= 2
    lines = text.splitlines()
    for row in ("oracle", "best single cheap", "strong", "Claude Code"):
        assert sum(1 for ln in lines if ln.startswith(f"| {row} |")) == 2
    assert text.index("## Oracle rule") < text.index("## View:")


def test_wrong_cwd_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert O.main([]) == 2
    assert "run from the repository root" in capsys.readouterr().err
