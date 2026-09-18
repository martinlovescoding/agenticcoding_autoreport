"""Multichannel engagement report generator.

The console script in `pyproject.toml` points at `main`, so `agenticcoding` on the
command line and `python -m agenticcoding` run the same thing. Both are wired through
`cli.main`, which returns an exit code rather than exiting, so it stays testable.
"""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return its exit code."""
    from .cli import main as run

    return run(argv)
