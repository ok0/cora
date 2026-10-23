"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import json
import os
import sys

ROOT = os.getcwd()
SCRATCH = os.path.join(ROOT, ".cora_grader")
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


def _answers():
    path = os.path.join(ROOT, "ANSWERS.json")
    assert os.path.isfile(path), "ANSWERS.json missing"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "ANSWERS.json is not a JSON object"
    return data


@check
def answers_file_valid():
    data = _answers()
    expect(sorted(data.keys()), ["q1", "q2", "q3", "q4", "q5"], "keys")


@check
def q1_attempts():
    value = _answers()["q1"]
    assert isinstance(value, (int, str)) and not isinstance(value, bool), "q1 has the wrong type"
    expect(int(str(value).strip()), 5, "q1")


@check
def q2_env_var():
    value = _answers()["q2"]
    assert isinstance(value, str), "q2 is not a string"
    expect(value.strip(), "RELAY_SPOOL_DIR", "q2")


@check
def q3_status():
    value = _answers()["q3"]
    assert isinstance(value, (int, str)) and not isinstance(value, bool), "q3 has the wrong type"
    expect(int(str(value).strip()), 410, "q3")


@check
def q4_function():
    value = _answers()["q4"]
    assert isinstance(value, str), "q4 is not a string"
    name = value.strip()
    if name.endswith("()"):
        name = name[:-2]
    expect(name, "is_transient_failure", "q4")


@check
def q5_delay():
    value = _answers()["q5"]
    assert isinstance(value, (int, float, str)) and not isinstance(value, bool), "q5 has the wrong type"
    assert abs(float(value) - 3.0) < 1e-9, f"q5: expected 3.0, got {value!r}"


def main():
    results = []
    for fn in CHECKS:
        try:
            fn()
            results.append({"name": fn.__name__, "passed": True, "detail": ""})
        except AssertionError as e:
            results.append({"name": fn.__name__, "passed": False, "detail": str(e)[:300]})
        except Exception as e:  # noqa: BLE001
            results.append({"name": fn.__name__, "passed": False, "detail": type(e).__name__})
    print(json.dumps({"checks": results}, sort_keys=True))


if __name__ == "__main__":
    main()
