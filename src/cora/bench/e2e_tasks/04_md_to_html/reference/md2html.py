"""Markdown to HTML - reference solution (tests only)."""

import re
import sys

HEADING = re.compile(r"(#{1,6}) (.*)$")
FENCE = "```"


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)


def _starts_block(line: str) -> bool:
    return (
        not line.strip()
        or line == FENCE
        or line.startswith("- ")
        or HEADING.match(line) is not None
    )


def convert(markdown: str) -> str:
    lines = markdown.split("\n")
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line == FENCE:
            j = i + 1
            while j < len(lines) and lines[j] != FENCE:
                j += 1
            body = "\n".join(escape(x) for x in lines[i + 1 : j])
            blocks.append(f"<pre><code>{body}</code></pre>")
            i = j + 1
        elif (m := HEADING.match(line)) is not None:
            level = len(m.group(1))
            blocks.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            i += 1
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:].strip())}</li>")
                i += 1
            blocks.append("\n".join(["<ul>", *items, "</ul>"]))
        else:
            parts = []
            while i < len(lines) and not _starts_block(lines[i]):
                parts.append(lines[i].strip())
                i += 1
            blocks.append(f"<p>{inline(' '.join(parts))}</p>")
    return "\n".join(blocks) + "\n" if blocks else ""


def main(argv: list[str]) -> int:
    with open(argv[0], encoding="utf-8") as f:
        sys.stdout.write(convert(f.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
