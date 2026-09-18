"""The two commands.

    agenticcoding generate --rows 200 --out data/raw_activities.csv
    agenticcoding report   --input data/raw_activities.csv --out report.html

`generate` is here so the report can be demonstrated on a dataset that is dirty in
exactly the ways the cleaner claims to handle. `report` is the deliverable.

Exit codes are the contract with a shell script: **0** success, **2** a usage error
(raised by `argparse`), **1** a runtime failure the user can act on — a missing file,
an unreadable one. Nothing here prints a traceback for a bad input path; the point of
a CLI is that a wrong argument is a message, not a stack.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from collections.abc import Sequence
from pathlib import Path

from . import clean, generate, report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agenticcoding",
        description="Turn a raw multichannel CRM export into a self-contained HTML report.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    make = commands.add_parser(
        "generate", help="write a synthetic raw export, deliberately dirty"
    )
    make.add_argument(
        "--rows", type=_positive, default=200, help="how many rows to write (default 200)"
    )
    make.add_argument("--seed", type=int, default=7, help="random seed (default 7)")
    make.add_argument("--out", required=True, help="path of the CSV to write")

    build = commands.add_parser("report", help="clean a CSV and render report.html")
    build.add_argument("--input", required=True, help="the raw CSV to read")
    build.add_argument("--out", required=True, help="path of the HTML page to write")
    build.add_argument(
        "--as-of",
        type=dt.date.fromisoformat,
        default=None,
        help="reference date for the 'future date' rule (default: today)",
    )
    build.add_argument(
        "--write-clean",
        default=None,
        help="also write the cleaned rows to this CSV (off by default)",
    )
    return parser


def _positive(text: str) -> int:
    """`--rows` must be at least one; a zero-row dataset is a usage error, not a report."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def _generate(args: argparse.Namespace) -> int:
    rows = generate.generate(args.rows, seed=args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    generate.write_raw(rows, out)
    print(f"wrote {len(rows)} raw rows to {out}", file=sys.stderr)
    return 0


def _report(args: argparse.Namespace) -> int:
    source = Path(args.input)
    try:
        header = clean.read_header(source)
        raw = clean.read_csv(source)
    except OSError as error:
        print(f"cannot read {source}: {error.strerror or error}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, csv.Error):
        print(f"{source} is not a readable CSV file", file=sys.stderr)
        return 1

    # A file that never names the id column is not one of these exports. Reporting
    # "0 interactions" for the wrong file would look like a clean result, not a mistake.
    if "interaction_id" not in header:
        print(
            f"{source} is not a raw activities export — its header names no "
            f"'interaction_id' column",
            file=sys.stderr,
        )
        return 1

    rows, quality = clean.clean_rows(raw, as_of=args.as_of)
    # Numeric, never `%d %B %Y`: the month *name* resolves against the process locale,
    # so the stamp would read differently on a German machine than on an English one.
    # The report's text must be a function of the CSV alone.
    generated_at = (args.as_of or dt.date.today()).strftime("%d.%m.%Y")

    slots = report.build_slots(
        rows, quality, source_file=str(source), generated_at=generated_at
    )
    page = report.document(slots, report.load_template())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

    if args.write_clean:
        clean.write_csv(rows, args.write_clean)

    kept = quality.rows_out
    print(
        f"{quality.rows_in} raw rows → {kept} analysable "
        f"({quality.analyzable_share:.0f} %) → {out}",
        file=sys.stderr,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line. Returns the exit code; raises `SystemExit` on a usage error."""
    args = _parser().parse_args(argv)
    if args.command == "generate":
        return _generate(args)
    return _report(args)
