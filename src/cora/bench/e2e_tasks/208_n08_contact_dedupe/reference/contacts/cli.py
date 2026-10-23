"""Command line entry point: python -m contacts.cli IN OUT."""

import csv
import sys

from .merge import dedupe
from .normalize import normalize_email, normalize_phone


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    in_path, out_path = args[0], args[1]
    try:
        with open(in_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])
            rows = [{k: (v or "") for k, v in row.items()} for row in reader]
    except OSError:
        print("error: cannot read IN", file=sys.stderr)
        return 1
    if "email" not in header:
        print("error: no email column", file=sys.stderr)
        return 2
    kept, removed = dedupe(rows)
    for row in kept:
        row["email"] = normalize_email(row["email"])
        if "phone" in header:
            row["phone"] = normalize_phone(row["phone"])
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(kept)
    print(f"kept {len(kept)}, removed {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
