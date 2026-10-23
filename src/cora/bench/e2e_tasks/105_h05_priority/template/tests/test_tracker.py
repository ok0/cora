from tracker.formatting import render
from tracker.models import Task
from tracker.service import Tracker
from tracker.storage import load, save


def test_existing_behaviour_kept(tmp_path):
    t = Tracker(str(tmp_path / "t.jsonl"))
    assert t.add("write").id == 1
    assert t.add("test").id == 2
    t.complete(2)
    assert [(x.id, x.title, x.done) for x in t.list()] == [(1, "write", False), (2, "test", True)]
    try:
        t.complete(9)
    except KeyError:
        pass
    else:
        assert False


def test_model_default_and_validation():
    assert Task(1, "a").priority == "normal"
    try:
        Task(1, "a", priority="urgent")
    except ValueError as e:
        assert str(e) == "invalid priority: urgent"
    else:
        assert False


def test_storage_roundtrip(tmp_path):
    path = str(tmp_path / "s.jsonl")
    assert load(path) == []
    tasks = [Task(1, "a"), Task(2, "b", True, "high")]
    save(path, tasks)
    assert load(path) == tasks


def test_formatting_marker():
    assert render([Task(1, "a"), Task(2, "b", True, "high")]) == "  1 [N] [ ] a\n  2 [H] [x] b"
