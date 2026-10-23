def slug(heading: str) -> str:
    """Return the anchor name for the text of a heading."""
    raise NotImplementedError


def toc(markdown: str, min_level: int = 1, max_level: int = 3) -> str:
    """Return the table of contents lines for the headings in markdown."""
    raise NotImplementedError
