from __future__ import annotations

from prompt_toolkit.formatted_text import FormattedText

from cora.cli.ui.theme import Theme


def prompt_message(prompt: str, theme: Theme) -> FormattedText:
    if prompt.startswith("[") and "] " in prompt:
        mode, sep, rest = prompt.partition("] ")
        return FormattedText([(theme.pt_mode, mode + sep), (theme.pt_marker, rest)])
    if prompt.rstrip().endswith(">"):
        return FormattedText([(theme.pt_marker, prompt)])
    return FormattedText([(theme.pt_dim, prompt)])
