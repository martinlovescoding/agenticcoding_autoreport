"""The two commands, end to end.

`generate` writes a deliberately dirty CSV; `report` turns one back into a
self-contained page. The tests run the real pipeline through `main`, because the
thing that matters is that the two commands fit together — a unit test of each half
would not notice that `report` never reads what `generate` wrote.
"""

import csv
import datetime as dt
import re
import subprocess
import sys

import pytest

from agenticcoding import cli, report

AS_OF = dt.date(2026, 9, 18)


# --- generate -----------------------------------------------------------------


def test_generate_writes_the_requested_number_of_rows(tmp_path):
    out = tmp_path / "raw.csv"

    assert cli.main(["generate", "--rows", "40", "--out", str(out)]) == 0

    with out.open(encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 40


def test_generate_is_reproducible(tmp_path):
    """Two runs at the same seed are byte-identical — the CSV is a fixture, not a draw."""
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"

    cli.main(["generate", "--rows", "60", "--out", str(first)])
    cli.main(["generate", "--rows", "60", "--out", str(second)])

    assert first.read_bytes() == second.read_bytes()


def test_generate_creates_the_output_directory(tmp_path):
    out = tmp_path / "nested" / "deeper" / "raw.csv"

    assert cli.main(["generate", "--rows", "5", "--out", str(out)]) == 0
    assert out.exists()


def test_generate_rejects_a_row_count_below_one(tmp_path, capsys):
    out = tmp_path / "raw.csv"

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["generate", "--rows", "0", "--out", str(out)])

    assert exit_info.value.code == 2, "a usage error, not a crash"
    assert not out.exists()


# --- report -------------------------------------------------------------------


@pytest.fixture
def raw_csv(tmp_path) -> str:
    path = tmp_path / "raw_activities.csv"
    cli.main(["generate", "--rows", "200", "--out", str(path)])
    return str(path)


def test_report_writes_a_self_contained_page(tmp_path, raw_csv):
    out = tmp_path / "report.html"

    assert cli.main(["report", "--input", raw_csv, "--out", str(out), "--as-of", "2026-09-18"]) == 0

    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert "{{" not in page, "an unfilled slot would render as a hole"


def test_report_pages_the_generated_csv_without_network_references(tmp_path, raw_csv):
    out = tmp_path / "report.html"
    cli.main(["report", "--input", raw_csv, "--out", str(out), "--as-of", "2026-09-18"])

    page = out.read_text(encoding="utf-8")
    assert "http://" not in page and "https://" not in page


def test_report_carries_the_cleaned_row_count_into_the_page(tmp_path, raw_csv):
    """The headline figure must be the number of rows that survived cleaning.

    Read back off the words in the page rather than off a class: a class name is the
    designer's to change, and a test that pins one turns every design swap into a
    suite of false failures. Whichever way the figure is styled, it is the number
    printed as the *Interactions* figure, so that is what this reads.
    """
    from agenticcoding import clean

    out = tmp_path / "report.html"
    cli.main(["report", "--input", raw_csv, "--out", str(out), "--as-of", "2026-09-18"])

    kept, quality = clean.clean_rows(clean.read_csv(raw_csv), as_of=AS_OF)
    assert len(kept) < quality.rows_in, "the fixture must lose rows, or the check proves nothing"

    text = re.sub(r"<[^>]+>", " ", out.read_text(encoding="utf-8"))
    assert re.search(rf"\b{len(kept)}\b[\s\S]{{0,80}}?Interactions", text), text[:400]


def test_report_does_not_write_the_cleaned_csv_unless_asked(tmp_path, raw_csv):
    out = tmp_path / "report.html"
    cleaned = tmp_path / "clean.csv"

    cli.main(["report", "--input", raw_csv, "--out", str(out), "--as-of", "2026-09-18"])

    assert not cleaned.exists()


def test_report_writes_the_cleaned_csv_on_request(tmp_path, raw_csv):
    out, cleaned = tmp_path / "report.html", tmp_path / "clean.csv"

    code = cli.main(
        [
            "report", "--input", raw_csv, "--out", str(out),
            "--write-clean", str(cleaned), "--as-of", "2026-09-18",
        ]
    )

    assert code == 0
    assert cleaned.exists()


def test_report_on_a_missing_input_explains_itself(tmp_path, capsys):
    missing = tmp_path / "nope.csv"

    assert cli.main(["report", "--input", str(missing), "--out", str(tmp_path / "r.html")]) == 1

    assert "nope.csv" in capsys.readouterr().err


def test_report_on_an_empty_csv_still_builds_a_page(tmp_path):
    """A CSV with headers and no data must render, not crash."""
    source = tmp_path / "empty.csv"
    source.write_text(
        "interaction_id,date,rep_name,hcp_id,specialty,channel,product,"
        "duration_min,engagement_score,opened,clicked\n",
        encoding="utf-8",
    )

    out = tmp_path / "report.html"
    assert cli.main(["report", "--input", str(source), "--out", str(out)]) == 0
    assert "{{" not in out.read_text(encoding="utf-8")


# --- the command line itself --------------------------------------------------


def test_no_arguments_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    assert exit_info.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_the_module_runs_as_a_command():
    """`python -m agenticcoding` is the documented entry point, so it must exist."""
    result = subprocess.run(
        [sys.executable, "-m", "agenticcoding", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "generate" in result.stdout
    assert "report" in result.stdout


def test_main_reports_a_broken_input_rather_than_a_traceback(tmp_path, capsys):
    """A file that is not a CSV should be a message, not a stack trace."""
    source = tmp_path / "binary.csv"
    source.write_bytes(b"\x00\x01\x02 not a csv at all")

    code = cli.main(["report", "--input", str(source), "--out", str(tmp_path / "r.html")])

    assert code == 1
    assert capsys.readouterr().err.strip()


def test_the_console_script_entry_point_is_wired_up():
    """`pyproject.toml` points the `agenticcoding` script at `agenticcoding:main`."""
    import agenticcoding

    assert callable(agenticcoding.main)
    assert callable(report.load_template)
