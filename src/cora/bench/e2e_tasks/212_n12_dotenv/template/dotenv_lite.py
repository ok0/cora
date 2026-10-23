"""Read and write simple .env files."""


def dump(d: dict[str, str]) -> str:
    return "".join(f"{k}={v}\n" for k, v in d.items())


def parse(text: str) -> dict[str, str]:
    """Parse .env text into a dict of key/value pairs, following REQUIREMENTS.md."""
    raise NotImplementedError
