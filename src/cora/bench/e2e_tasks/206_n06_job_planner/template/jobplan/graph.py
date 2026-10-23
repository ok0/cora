from .model import Job


def validate(jobs: list[Job]) -> None:
    """Raise JobError for unknown dependencies or cycles."""
    raise NotImplementedError


def order(jobs: list[Job]) -> list[str]:
    """Return job names in dispatch order."""
    raise NotImplementedError
