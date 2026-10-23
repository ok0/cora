from .model import Job, JobError


def _reach(by_name: dict[str, Job]) -> dict[str, set[str]]:
    reach: dict[str, set[str]] = {}
    for start in by_name:
        seen: set[str] = set()
        stack = list(by_name[start].deps)
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(by_name[node].deps)
        reach[start] = seen
    return reach


def _cycle_path(start: str, by_name: dict[str, Job]) -> list[str]:
    path = [start]

    def walk(cur: str) -> bool:
        for dep in sorted(by_name[cur].deps):
            if dep == start:
                return True
            if dep in path:
                continue
            path.append(dep)
            if walk(dep):
                return True
            path.pop()
        return False

    walk(start)
    return path + [start]


def validate(jobs: list[Job]) -> None:
    by_name = {j.name: j for j in jobs}
    for job in jobs:
        for dep in job.deps:
            if dep not in by_name:
                raise JobError(f"job '{job.name}' depends on unknown '{dep}'")
    reach = _reach(by_name)
    on_cycle = [name for name in by_name if name in reach[name]]
    if not on_cycle:
        return
    start = min(on_cycle)
    raise JobError("cycle: " + " -> ".join(_cycle_path(start, by_name)))


def order(jobs: list[Job]) -> list[str]:
    validate(jobs)
    done: set[str] = set()
    pending = list(jobs)
    result: list[str] = []
    while pending:
        ready = [j for j in pending if all(d in done for d in j.deps)]
        best = min(ready, key=lambda j: (-j.priority, j.name))
        result.append(best.name)
        done.add(best.name)
        pending = [j for j in pending if j is not best]
    return result
