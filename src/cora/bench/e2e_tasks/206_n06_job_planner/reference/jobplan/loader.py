import json

from .model import Job, JobError


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_jobs(text: str) -> list[Job]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise JobError("invalid JSON") from None
    if not isinstance(data, list):
        raise JobError("expected a JSON array")
    jobs: list[Job] = []
    names: set[str] = set()
    for i, item in enumerate(data, start=1):
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name:
            raise JobError(f"job {i}: missing name")
        duration = item.get("duration")
        if not _is_int(duration) or duration < 1:
            raise JobError(f"job {i}: duration must be a positive integer")
        deps = item.get("deps", [])
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise JobError(f"job {i}: deps must be a list of names")
        priority = item.get("priority", 0)
        if not _is_int(priority):
            raise JobError(f"job {i}: priority must be an integer")
        if name in names:
            raise JobError(f"duplicate job '{name}'")
        names.add(name)
        jobs.append(Job(name, duration, tuple(deps), priority))
    return jobs
