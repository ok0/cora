from .model import Job, Schedule


def simulate(jobs: list[Job], workers: int) -> Schedule:
    """Run the jobs on the given number of workers and return the schedule."""
    raise NotImplementedError
