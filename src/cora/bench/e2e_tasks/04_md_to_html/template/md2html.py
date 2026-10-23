"""Markdown to HTML converter - see REQUIREMENTS.md."""

import sys


def convert(markdown: str) -> str:
    raise NotImplementedError


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        sys.stdout.write(convert(f.read()))
