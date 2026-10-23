"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import importlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


def raises(exc, fn, *args):
    try:
        fn(*args)
    except exc as e:
        return e
    raise AssertionError(f"{exc.__name__} not raised")


def workdir():
    os.makedirs(os.path.join(ROOT, ".cora_grader"), exist_ok=True)
    return tempfile.mkdtemp(dir=os.path.join(ROOT, ".cora_grader"))


def norm():
    return importlib.import_module("contacts.normalize")


def merge():
    return importlib.import_module("contacts.merge")


def cli_run(*args):
    return subprocess.run(
        [sys.executable, "-B", "-m", "contacts.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


ROWS = [
    {"name": "John", "email": "john.doe@gmail.com", "phone": ""},
    {"name": "", "email": "Mary@x.org", "phone": "555 000 1111"},
    {"name": "Johnny", "email": "JohnDoe+a@gmail.com", "phone": "5551234567"},
    {"name": "Nobody", "email": "", "phone": "1"},
    {"name": "N2", "email": "", "phone": "2"},
    {"name": "Mary", "email": "mary@x.org", "phone": ""},
]


@check
def email_gmail_rules():
    ne = norm().normalize_email
    expect(ne("  John.Doe+news@GMail.com "), "johndoe@gmail.com", "gmail with plus and dots")
    expect(ne("j.d@googlemail.com"), "jd@gmail.com", "googlemail domain")


@check
def email_other_domains():
    ne = norm().normalize_email
    expect(ne("Mary.Ann+x@Example.org"), "mary.ann+x@example.org", "other domain keeps dots and plus")
    expect(ne("NoAt "), "noat", "no at sign")


@check
def phone_rules():
    np_ = norm().normalize_phone
    expect(np_("(555) 123-4567"), "+15551234567", "ten digits")
    expect(np_("0044 20 7946 0958"), "+442079460958", "double zero prefix")
    expect(np_("+44 20 7946 0958"), "+442079460958", "plus prefix")
    expect(np_("12345"), "+12345", "short digits")
    expect(np_("n/a"), "", "no digits")


@check
def dedupe_keep_first_and_fill():
    kept, removed = merge().dedupe([dict(r) for r in ROWS])
    expect(kept, [
        {"name": "John", "email": "john.doe@gmail.com", "phone": "5551234567"},
        {"name": "Mary", "email": "Mary@x.org", "phone": "555 000 1111"},
        {"name": "Nobody", "email": "", "phone": "1"},
        {"name": "N2", "email": "", "phone": "2"},
    ], "kept rows")
    expect(removed, 2, "removed count")


@check
def empty_email_never_merged():
    rows = [dict(ROWS[3]), dict(ROWS[4])]
    kept, removed = merge().dedupe(rows)
    expect(kept, [ROWS[3], ROWS[4]], "empty email rows kept")
    expect(removed, 0, "removed count")


@check
def cli_output_file():
    d = workdir()
    src = os.path.join(d, "in.csv")
    out = os.path.join(d, "out.csv")
    with open(src, "w", newline="", encoding="utf-8") as f:
        f.write(
            "name,email,phone\n"
            "John,john.doe@gmail.com,\n"
            ",Mary@x.org,555 000 1111\n"
            "Johnny,JohnDoe+a@gmail.com,5551234567\n"
            "Nobody,,1\n"
            "N2,,2\n"
            "Mary,mary@x.org,\n"
        )
    r = cli_run(src, out)
    expect(r.returncode, 0, "exit code")
    expect(r.stdout.strip(), "kept 4, removed 2", "stdout")
    with open(out, "rb") as f:
        text = f.read().decode("utf-8")
    expect(text, (
        "name,email,phone\r\n"
        "John,johndoe@gmail.com,+15551234567\r\n"
        "Mary,mary@x.org,+15550001111\r\n"
        "Nobody,,+1\r\n"
        "N2,,+2\r\n"
    ), "output file")


@check
def cli_errors():
    d = workdir()
    src = os.path.join(d, "no_email.csv")
    out = os.path.join(d, "out.csv")
    with open(src, "w", newline="", encoding="utf-8") as f:
        f.write("name,phone\nJohn,1\n")
    r = cli_run(src, out)
    expect(r.returncode, 2, "no email column exit code")
    expect(r.stderr.strip(), "error: no email column", "no email column message")
    expect(os.path.exists(out), False, "no output written")
    r = cli_run(os.path.join(d, "missing.csv"), out)
    expect(r.returncode, 1, "missing input exit code")
    expect(r.stderr.strip(), "error: cannot read IN", "missing input message")


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
