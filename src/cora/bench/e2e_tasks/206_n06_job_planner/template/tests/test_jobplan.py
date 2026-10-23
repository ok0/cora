from jobplan import Job, order, simulate


def _example():
    return [
        Job("fetch", 2),
        Job("build", 3, ("fetch",)),
        Job("lint", 1, (), 5),
        Job("test", 4, ("build",), 1),
        Job("docs", 2, ("fetch",)),
    ]


def test_order_example():
    assert order(_example()) == ["lint", "fetch", "build", "test", "docs"]


def test_simulate_one_worker():
    s = simulate(_example(), 1)
    assert s.starts == {"lint": 0, "fetch": 1, "build": 3, "test": 6, "docs": 10}
    assert s.makespan == 12
