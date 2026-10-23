# Markdown to HTML converter

Implement `convert(markdown: str) -> str` in `md2html.py` (standard library only).
The rules below are exact.

- **Command line and output:**
  - CLI: `python md2html.py FILE` writes `convert(contents)` via `sys.stdout.write` with no extra newline.
  - Input is split on `"\n"`.
  - Output is the blocks joined with `"\n"` plus a final `"\n"`, or `""` when there are no blocks.
- **Blocks:**
  - **Code fence:** a line that is exactly ``` (three backticks) up to the next such line (an unclosed fence runs to the end) → `<pre><code>` + the inner lines, HTML-escaped and joined with `"\n"`, with no inline formatting + `</code></pre>`.
  - **Heading:** 1–6 `#`, a space, then text → `<hN>text</hN>`.
  - **List:** consecutive lines starting with `- ` → `<ul>` / `<li>item</li>`… / `</ul>`, each on its own line.
  - **Blank lines** (empty or spaces only) separate blocks.
  - **Paragraph:** any other run of lines, each stripped and joined with one space → `<p>…</p>`. A paragraph ends at a blank line, heading, list line or fence.
- **Inline formatting** applies to headings, list items and paragraphs, in this order:
  1. escape `&` `<` `>`
  2. `` `code` `` → `<code>`
  3. `**b**` → `<strong>`
  4. `*e*` → `<em>`
  5. `[text](url)` → `<a href="url">text</a>`
