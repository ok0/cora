from __future__ import annotations

import argparse
import sys

from tracker.formatting import render
from tracker.models import PRIORITIES
from tracker.service import Tracker


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="tracker")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    add_p = sub.add_parser("add")
    add_p.add_argument("title")
    add_p.add_argument("--priority", choices=PRIORITIES, default="normal")
    list_p = sub.add_parser("list")
    list_p.add_argument("--sort", choices=["id", "priority"], default="id")
    done_p = sub.add_parser("done")
    done_p.add_argument("id", type=int)
    args = parser.parse_args(argv)
    svc = Tracker(args.db)
    if args.command == "add":
        task = svc.add(args.title, priority=args.priority)
        print(f"added {task.id}")
        return 0
    if args.command == "list":
        print(render(svc.list(sort=args.sort)))
        return 0
    try:
        svc.complete(args.id)
    except KeyError:
        print(f"error: no task {args.id}", file=sys.stderr)
        return 1
    print(f"done {args.id}")
    return 0
