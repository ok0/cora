from __future__ import annotations

GAP_RULES = frozenset(
    {"confine:one-liner", "confine:shell-c", "confine:interpreter-stdin", "floor:pipe-exec"}
)

ONE = "confine:one-liner"
SHELL_C = "confine:shell-c"
STDIN = "confine:interpreter-stdin"
PIPE = "floor:pipe-exec"
SAME = "="

GAP_FORMS: dict[str, str] = {
    "perl -pe x README.md": ONE,
    "perl -ne 'print' README.md": ONE,
    "ruby -ne x": ONE,
    "node -pe x": ONE,
    "pwsh -Comm x": ONE,
    "pwsh -ec x": ONE,
    "deno -A eval x": ONE,
    "busybox sh -c ls": SHELL_C,
}

CLOSED_FORM: dict[str, str] = {
    "perl -pe x README.md": "perl -e x README.md",
    "perl -ne 'print' README.md": "perl -e 'print' README.md",
    "ruby -ne x": "ruby -e x",
    "node -pe x": "node -p x",
    "pwsh -Comm x": "pwsh -Command x",
    "pwsh -ec x": "pwsh -EncodedCommand x",
    "deno -A eval x": "deno eval x",
    "busybox sh -c ls": "sh -c ls",
}

_CLUSTER_ONE = (
    "perl -lne x README.md",
    "perl -0777ne x README.md",
    "perl -nE x README.md",
    "perl -w -ne x README.md",
    "perl -i -pe x README.md",
    "perl -Mstrict -ne x README.md",
    "perl -F: -lane x README.md",
    "perl '-ne' x README.md",
    'perl -ne "print" README.md',
    "env perl -ne x README.md",
    "time perl -pe x README.md",
    "ls; perl -ne x README.md",
    "cat README.md | perl -ne x",
    "perl -ne x README.md > out.txt",
    "ruby -pe x",
    "ruby -w -ne x",
    "ruby -rjson -ne x",
    "ruby -r json -ne x",
    "ruby -lane x",
    "'ruby' -ne x",
    "nice -n 5 ruby -ne x",
    "ls && ruby -ne x",
    "node -ep x",
    "node -ip x",
    "node -rp x",
    "node --no-warnings -pe x",
    "nodejs -pe x",
    "env node -pe x",
    "node '-pe' x",
    "ls | node -pe x",
    "node -pe x 2>&1",
)

_ABBREV_ONE = (
    "pwsh -co x",
    "pwsh -com x",
    "pwsh -comma x",
    "pwsh -COMM x",
    "pwsh -e x",
    "pwsh -en x",
    "pwsh -enc x",
    "pwsh -EncodedC x",
    "pwsh -NoProfile -Comm x",
    "pwsh -NoLogo -ec x",
    "pwsh '-Comm' x",
    "env pwsh -comm x",
    "ls; pwsh -ec x",
    "pwsh -Comm x > out.txt",
)

_SUBCOMMAND_ONE = (
    "deno -q eval x",
    "deno --quiet eval x",
    "deno -A repl",
    "deno --unstable repl",
    "deno -L debug eval x",
    "deno --log-level debug eval x",
    "deno --log-level=debug eval x",
    "deno '-A' eval x",
    "env deno -A eval x",
    "ls && deno -A eval x",
    "deno -A -q eval x",
)

_APPLET_SHELL_C = (
    "busybox sh -c 'ls'",
    "busybox ash -c ls",
    "busybox bash -c ls",
    "busybox sh -xc ls",
    "busybox sh -e -c ls",
    "busybox 'sh' -c ls",
    "busybox busybox sh -c ls",
    "time busybox ash -c ls",
    "env busybox sh -c ls",
    "ls; busybox sh -c ls",
)

VARIANTS: dict[str, dict[str, str]] = {
    "cluster": {
        **{c: ONE for c in _CLUSTER_ONE},
        "/usr/bin/perl -ne x README.md": SAME,
        "(ruby -ne x)": SAME,
        "/usr/local/bin/node -pe x": SAME,
    },
    "abbrev": {
        **{c: ONE for c in _ABBREV_ONE},
        "/usr/local/bin/pwsh -Comm x": SAME,
    },
    "subcommand": {
        **{c: ONE for c in _SUBCOMMAND_ONE},
        "/usr/local/bin/deno -A eval x": SAME,
        "(deno -q eval x)": SAME,
    },
    "applet": {
        **{c: SHELL_C for c in _APPLET_SHELL_C},
        "busybox sh -s": STDIN,
        "busybox sh -": STDIN,
        "busybox sh": STDIN,
        "echo ls | busybox sh": PIPE,
        "/bin/busybox sh -c ls": SAME,
    },
}

CONTROLS: dict[str, tuple[str, ...]] = {
    "cluster": (
        "perl -w script.pl",
        "perl -Mfeature=say script.pl",
        "perl -mfeature script.pl",
        "perl -CSDe script.pl",
        "perl -d:Trace script.pl",
        "perl -Dtle script.pl",
        "perl -Fe script.pl",
        "perl -i.e script.pl",
        "perl -Ilibe script.pl",
        "perl -V:version",
        "perl -xe script.pl",
        "perl -c script.pl",
        "perl script.pl -verbose",
        "perl5 -ne x",
        "ruby -Ce script.rb",
        "ruby -Eeuc-jp script.rb",
        "ruby -Fe script.rb",
        "ruby -Ilibe script.rb",
        "ruby -i.e script.rb",
        "ruby -Ke script.rb",
        "ruby -rset script.rb",
        "ruby -xe script.rb",
        "ruby -w script.rb",
        "node -c script.js",
        "node -Cdevelopment script.js",
        "node18 -pe x",
    ),
    "abbrev": (
        "pwsh -File s.ps1",
        "pwsh -f s.ps1",
        "pwsh -ex Bypass -File s.ps1",
        "pwsh -ep Bypass -File s.ps1",
        "pwsh -NoProfile -File s.ps1",
        "pwsh -config x -File s.ps1",
        "pwsh -commandx x",
    ),
    "subcommand": (
        "deno run script.ts",
        "deno test",
        "denox eval x",
        "deno -A run script.ts",
        "deno -q test",
        "deno --version",
        "deno -q run eval",
        "deno -L debug run script.ts",
        "deno fmt",
    ),
    "applet": (
        "busybox ls",
        "busybox sh script.sh",
        "busybox ls -c",
        "busybox awk 'NR==1' README.md",
        "busybox sed -n 1p README.md",
        "busybox shx -c ls",
        "busybox -c ls",
        "busybox",
    ),
}

ROUTED: dict[str, str] = {
    "pwsh --command x": "double-dash spelling, not an abbreviation",
    "pwsh -CommandWithArgs x": "separate pwsh parameter that runs a command",
    "pwsh -cwa x": "separate pwsh parameter that runs a command",
    "deno -A": (
        "flags without a subcommand; denying flag-only deno would also deny `deno --version`"
    ),
    "busybox awk 'BEGIN{}'": "non-shell applet that runs program text; A3 keeps non-shell applets",
    "bun -pe x": "bun not in Q2; no evidence that bun clusters flags",
    "perl script.pl -ne x": "cluster after the script operand is a script argument",
}

GAP_FAMILY = frozenset(GAP_FORMS) | frozenset(c for fam in VARIANTS.values() for c in fam)

PINNED = frozenset(c for ctl in CONTROLS.values() for c in ctl) | frozenset(ROUTED)

ALL: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            *GAP_FORMS,
            *(c for fam in VARIANTS.values() for c in fam),
            *(c for ctl in CONTROLS.values() for c in ctl),
            *ROUTED,
        ]
    )
)

EXPECTED: dict[str, str] = {
    **GAP_FORMS,
    **{cmd: rule for fam in VARIANTS.values() for cmd, rule in fam.items()},
}
