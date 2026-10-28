"""Command-line entry point: `aidlc <command>`.

Every command prints a short plain-language result for a PM. Exit code is
0 on success and 1 when something needs attention.
"""

import argparse
import sys
from pathlib import Path

from aidlc.config import find_root
from aidlc.validate import refresh_statuses, validate_repo


def cmd_validate(args: argparse.Namespace) -> int:
    root = find_root(Path(args.root))
    if args.write:
        for change in refresh_statuses(root):
            a = change.artifact
            print(f"Marked {a.feature}/{a.id} as {change.new} (was {change.old}).")

    report = validate_repo(root)
    for issue in report.errors + report.warnings:
        print(f"  {'✗' if issue.severity == 'error' else '!'} {issue.where}: {issue.message}")

    n = len(report.artifacts)
    if report.ok:
        extra = f", with {len(report.warnings)} warning(s)" if report.warnings else ""
        print(f"All {n} artifact(s) are valid{extra}.")
        return 0
    print(f"Found {len(report.errors)} problem(s) across {n} artifact(s). Fix them and run validate again.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aidlc", description="AIDLC Kit workflow commands.")
    parser.add_argument("--root", default=".", help="repository folder (default: current folder)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check every artifact in the repository")
    p.add_argument("--write", action="store_true", help="write computed stale/draft statuses first")
    p.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
