from .model import Schedule


def render(s: Schedule) -> str:
    rows = sorted(s.starts, key=lambda n: (s.starts[n], s.worker[n]))
    lines = [f"{s.starts[n]:>4} {s.ends[n]:>4}  w{s.worker[n]}  {n}" for n in rows]
    lines.append(f"makespan {s.makespan}")
    return "\n".join(lines) + "\n"
