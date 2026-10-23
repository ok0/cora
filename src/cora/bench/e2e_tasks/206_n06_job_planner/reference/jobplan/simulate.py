from .graph import validate
from .model import Job, Schedule


def simulate(jobs: list[Job], workers: int) -> Schedule:
    if workers < 1:
        raise ValueError("workers must be >= 1")
    validate(jobs)
    pending = list(jobs)
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    worker: dict[str, int] = {}
    running: dict[int, int] = {}
    free = set(range(workers))
    t = 0
    while pending or running:
        for w in [w for w, end in running.items() if end <= t]:
            del running[w]
            free.add(w)
        ready = [j for j in pending if all(d in ends and ends[d] <= t for d in j.deps)]
        ready.sort(key=lambda j: (-j.priority, j.name))
        for job in ready:
            if not free:
                break
            w = min(free)
            free.remove(w)
            starts[job.name] = t
            ends[job.name] = t + job.duration
            worker[job.name] = w
            running[w] = t + job.duration
            pending = [p for p in pending if p is not job]
        if running:
            t = min(running.values())
    makespan = max(ends.values(), default=0)
    return Schedule(starts, ends, worker, makespan)
