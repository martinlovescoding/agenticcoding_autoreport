"""The cleaning pipeline: one test per stage, plus the invariants that hold across it."""

import datetime as dt

import pytest

from agenticcoding import schema
from agenticcoding.clean import clean_rows, read_csv, read_header, write_csv
from conftest import AS_OF, raw_row


def count(report, key: str) -> int:
    """Read one stage counter by its stable key."""
    return report.count(key)


# --- identity: a clean row survives untouched ---------------------------------


def test_a_clean_row_is_returned_unchanged(as_of):
    cleaned, report = clean_rows([raw_row()], as_of=as_of)

    assert len(cleaned) == 1
    row = cleaned[0]
    assert row.interaction_id == "I001"
    assert row.date == dt.date(2026, 3, 2)
    assert row.channel == "F2F Call"
    assert row.specialty == "Oncology"
    assert row.duration_min == 30
    assert row.engagement_score == 80.0
    assert row.opened is True
    assert row.clicked is False
    assert report.rows_in == 1
    assert report.rows_out == 1


# --- stage: duplicates --------------------------------------------------------


def test_duplicate_interaction_id_keeps_the_first_occurrence(as_of):
    rows = [
        raw_row(interaction_id="I001", engagement_score="80"),
        raw_row(interaction_id="I001", engagement_score="10"),
    ]

    cleaned, report = clean_rows(rows, as_of=as_of)

    assert len(cleaned) == 1
    assert cleaned[0].engagement_score == 80.0, "the first occurrence must win"
    assert count(report, "duplicates") == 1


def test_row_without_interaction_id_is_dropped(as_of):
    cleaned, report = clean_rows([raw_row(interaction_id="")], as_of=as_of)

    assert cleaned == []
    assert count(report, "id_missing") == 1


# --- stage: channels ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_channel", "expected"),
    [
        ("F2F Call", "F2F Call"),
        ("f2f", "F2F Call"),
        ("  F2F   call ", "F2F Call"),
        ("face-to-face", "F2F Call"),
        ("S2S", "Screen-to-Screen Call"),
        ("Screen-to-Screen", "Screen-to-Screen Call"),
        ("rep-email", "Rep Email"),
        ("HQ_Email", "HQ Email"),
        ("webinar", "Web"),
        ("congress", "Event"),
        ("Telefon", "Phone Call"),
    ],
)
def test_channel_variants_map_to_the_canonical_channel(as_of, raw_channel, expected):
    cleaned, _ = clean_rows([raw_row(channel=raw_channel)], as_of=as_of)

    assert cleaned[0].channel == expected


def test_only_non_canonical_spellings_are_counted_as_normalized(as_of):
    rows = [
        raw_row(interaction_id="I001", channel="F2F Call"),  # already canonical
        raw_row(interaction_id="I002", channel="f2f"),  # variant
    ]

    _, report = clean_rows(rows, as_of=as_of)

    assert count(report, "channels") == 1


def test_unrecognized_channel_drops_the_row(as_of):
    cleaned, report = clean_rows([raw_row(channel="Carrier Pigeon")], as_of=as_of)

    assert cleaned == []
    assert count(report, "unknown_channel") == 1


# --- stage: specialties -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_specialty", "expected"),
    [
        ("Onkologie", "Oncology"),
        ("oncology", "Oncology"),
        ("Kardiologie", "Cardiology"),
        ("Allgemeinmedizin", "General Medicine"),
        ("gp", "General Medicine"),
        ("Pneumologie", "Pulmonology"),
        ("Diabetologie", "Diabetology"),
    ],
)
def test_specialty_variants_map_to_the_canonical_specialty(as_of, raw_specialty, expected):
    cleaned, _ = clean_rows([raw_row(specialty=raw_specialty)], as_of=as_of)

    assert cleaned[0].specialty == expected


def test_specialty_spelling_fixes_are_counted(as_of):
    rows = [
        raw_row(interaction_id="I001", specialty="Oncology"),
        raw_row(interaction_id="I002", specialty="Onkologie"),
    ]

    _, report = clean_rows(rows, as_of=as_of)

    assert count(report, "specialties") == 1


# --- stage: dates -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_date", "expected"),
    [
        ("2026-03-02", dt.date(2026, 3, 2)),
        ("02.03.2026", dt.date(2026, 3, 2)),
        ("03/02/2026", dt.date(2026, 3, 2)),
        ("2026/03/02", dt.date(2026, 3, 2)),
    ],
)
def test_date_formats_are_parsed(as_of, raw_date, expected):
    cleaned, _ = clean_rows([raw_row(date=raw_date)], as_of=as_of)

    assert cleaned[0].date == expected


def test_slash_dates_are_read_month_first(as_of):
    """Documented convention: 04/03/2026 is 3 April, not 4 March."""
    cleaned, _ = clean_rows([raw_row(date="04/03/2026")], as_of=as_of)

    assert cleaned[0].date == dt.date(2026, 4, 3)


@pytest.mark.parametrize("raw_date", ["", "   ", "not a date", "2026-13-45", "32.13.2026"])
def test_missing_or_invalid_date_drops_the_row(as_of, raw_date):
    cleaned, report = clean_rows([raw_row(date=raw_date)], as_of=as_of)

    assert cleaned == []
    assert count(report, "dates_invalid") == 1


def test_future_date_drops_the_row(as_of):
    cleaned, report = clean_rows([raw_row(date="2026-12-01")], as_of=as_of)

    assert cleaned == []
    assert count(report, "dates_future") == 1


def test_date_equal_to_as_of_is_not_future(as_of):
    cleaned, _ = clean_rows([raw_row(date="2026-09-18")], as_of=as_of)

    assert len(cleaned) == 1


# --- stage: duration ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_duration", "expected"),
    [("30", 30), ("45 min", 45), (" 45 ", 45), ("30.0", 30), ("", None), ("n/a", None)],
)
def test_duration_is_coerced(as_of, raw_duration, expected):
    cleaned, _ = clean_rows([raw_row(duration_min=raw_duration)], as_of=as_of)

    assert cleaned[0].duration_min == expected


def test_negative_duration_is_corrected_by_absolute_value(as_of):
    cleaned, report = clean_rows([raw_row(duration_min="-12")], as_of=as_of)

    assert cleaned[0].duration_min == 12
    assert count(report, "duration_negative") == 1


def test_implausible_duration_becomes_missing(as_of):
    cleaned, report = clean_rows([raw_row(duration_min="900")], as_of=as_of)

    assert cleaned[0].duration_min is None
    assert count(report, "duration_implausible") == 1


def test_duration_at_the_plausibility_limit_is_kept(as_of):
    cleaned, _ = clean_rows([raw_row(duration_min="300")], as_of=as_of)

    assert cleaned[0].duration_min == 300


# --- stage: engagement score --------------------------------------------------


@pytest.mark.parametrize(
    ("raw_score", "expected"),
    [("80", 80.0), ("56,3", 56.3), ("56.3", 56.3), ("", None), ("n/a", None)],
)
def test_engagement_score_is_coerced(as_of, raw_score, expected):
    cleaned, _ = clean_rows([raw_row(engagement_score=raw_score)], as_of=as_of)

    assert cleaned[0].engagement_score == expected


@pytest.mark.parametrize(("raw_score", "expected"), [("140", 100.0), ("-5", 0.0)])
def test_engagement_score_is_clamped(as_of, raw_score, expected):
    cleaned, report = clean_rows([raw_row(engagement_score=raw_score)], as_of=as_of)

    assert cleaned[0].engagement_score == expected
    assert count(report, "engagement_clamped") == 1


def test_score_inside_the_range_is_not_counted_as_clamped(as_of):
    _, report = clean_rows([raw_row(engagement_score="80")], as_of=as_of)

    assert count(report, "engagement_clamped") == 0


# --- stage: labels ------------------------------------------------------------


@pytest.mark.parametrize("raw_product", ["", "  ", "n/a"])
def test_missing_product_becomes_unknown(as_of, raw_product):
    cleaned, report = clean_rows([raw_row(product=raw_product)], as_of=as_of)

    assert cleaned[0].product == schema.UNKNOWN_PRODUCT
    assert count(report, "product_missing") == 1


def test_missing_rep_becomes_unassigned(as_of):
    cleaned, report = clean_rows([raw_row(rep_name="")], as_of=as_of)

    assert cleaned[0].rep_name == schema.UNKNOWN_REP
    assert count(report, "rep_missing") == 1


# --- stage: booleans ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_flag", "expected"),
    [
        ("Y", True),
        ("yes", True),
        ("1", True),
        ("true", True),
        ("N", False),
        ("no", False),
        ("0", False),
        ("false", False),
        ("", None),
        ("n/a", None),
    ],
)
def test_open_and_click_flags_are_coerced(as_of, raw_flag, expected):
    cleaned, _ = clean_rows([raw_row(opened=raw_flag, clicked=raw_flag)], as_of=as_of)

    assert cleaned[0].opened is expected
    assert cleaned[0].clicked is expected


# --- invariants ---------------------------------------------------------------


def test_rows_out_equals_rows_in_minus_every_drop(as_of):
    rows = [
        raw_row(interaction_id="I001"),
        raw_row(interaction_id="I001"),  # duplicate
        raw_row(interaction_id="", ),  # no id
        raw_row(interaction_id="I003", channel="Carrier Pigeon"),
        raw_row(interaction_id="I004", date="garbage"),
        raw_row(interaction_id="I005", date="2027-01-01"),
        raw_row(interaction_id="I006"),
    ]

    cleaned, report = clean_rows(rows, as_of=as_of)

    dropped = sum(
        report.count(key)
        for key in ("duplicates", "id_missing", "unknown_channel", "dates_invalid", "dates_future")
    )
    assert report.rows_in == 7
    assert report.rows_out == len(cleaned) == 2
    assert report.rows_out == report.rows_in - dropped


def test_cleaning_is_idempotent(as_of):
    """Cleaning already-clean rows must change nothing and count nothing."""
    rows = [
        raw_row(interaction_id="I001", channel="f2f", specialty="Onkologie", duration_min="-12"),
        raw_row(interaction_id="I002", engagement_score="140", product=""),
    ]
    first, _ = clean_rows(rows, as_of=as_of)

    second, report = clean_rows([_as_raw(row) for row in first], as_of=as_of)

    assert second == first
    assert all(note.count == 0 for note in report.notes), report.notes


def test_output_is_sorted_by_date_then_id(as_of):
    rows = [
        raw_row(interaction_id="I003", date="2026-05-01"),
        raw_row(interaction_id="I001", date="2026-03-01"),
        raw_row(interaction_id="I002", date="2026-03-01"),
    ]

    cleaned, _ = clean_rows(rows, as_of=as_of)

    assert [row.interaction_id for row in cleaned] == ["I001", "I002", "I003"]


def test_header_variants_are_normalized(as_of):
    row = raw_row()
    row[" Interaction_ID "] = row.pop("interaction_id")
    row["CHANNEL"] = row.pop("channel")

    cleaned, _ = clean_rows([row], as_of=as_of)

    assert cleaned[0].interaction_id == "I001"
    assert cleaned[0].channel == "F2F Call"


def test_empty_input_yields_empty_output(as_of):
    cleaned, report = clean_rows([], as_of=as_of)

    assert cleaned == []
    assert report.rows_in == 0
    assert report.rows_out == 0


def test_every_stage_is_reported_even_at_zero(as_of):
    """The quality table has a stable row set, so a zero still gets a line."""
    _, report = clean_rows([raw_row()], as_of=as_of)

    keys = [note.key for note in report.notes]
    assert keys == [
        "duplicates",
        "id_missing",
        "channels",
        "unknown_channel",
        "specialties",
        "dates_invalid",
        "dates_future",
        "duration_negative",
        "duration_implausible",
        "engagement_clamped",
        "product_missing",
        "rep_missing",
    ]


# --- csv round-trip -----------------------------------------------------------


def _as_raw(row: schema.Interaction) -> dict[str, str]:
    """Render a cleaned row back to raw text, as a CSV round-trip would."""
    return {
        "interaction_id": row.interaction_id,
        "date": row.date.isoformat(),
        "rep_name": row.rep_name,
        "hcp_id": row.hcp_id,
        "specialty": row.specialty,
        "channel": row.channel,
        "product": row.product,
        "duration_min": "" if row.duration_min is None else str(row.duration_min),
        "engagement_score": "" if row.engagement_score is None else str(row.engagement_score),
        "opened": "" if row.opened is None else ("Y" if row.opened else "N"),
        "clicked": "" if row.clicked is None else ("Y" if row.clicked else "N"),
    }


def test_csv_round_trip_preserves_the_cleaned_rows(tmp_path, as_of):
    rows = [raw_row(interaction_id="I001"), raw_row(interaction_id="I002", channel="S2S")]
    cleaned, _ = clean_rows(rows, as_of=as_of)
    path = tmp_path / "clean.csv"

    write_csv(cleaned, path)
    reread, _ = clean_rows(read_csv(path), as_of=as_of)

    assert reread == cleaned


def test_read_csv_strips_a_utf8_bom(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text("﻿interaction_id,channel\nI001,F2F Call\n", encoding="utf-8")

    rows = read_csv(path)

    assert rows[0]["interaction_id"] == "I001"


# --- the header of a file, read on its own ------------------------------------


def test_read_header_finds_the_id_column_under_a_verbose_spelling(tmp_path):
    """The CLI's gate is `"interaction_id" in header`, so a header must arrive normalized.

    A spreadsheet export writes ` Interaction ID `; read as written it names no id column,
    and a perfectly good file is rejected as the wrong one.
    """
    path = tmp_path / "raw.csv"
    path.write_text(
        " Interaction ID ,Date,Duration-Min\nI001,2026-03-02,30\n", encoding="utf-8"
    )

    assert read_header(path) == ["interaction_id", "date", "duration_min"]


def test_read_header_reads_a_header_only_export(tmp_path):
    """A filtered export has columns and no rows: an empty report, not a broken file."""
    path = tmp_path / "empty.csv"
    path.write_text("interaction_id,date,channel\n", encoding="utf-8")

    assert read_header(path) == ["interaction_id", "date", "channel"]


def test_read_header_strips_a_utf8_bom(tmp_path):
    """Excel writes one. Left on, the first column is `\\ufeffinteraction_id` and the file fails the gate."""
    path = tmp_path / "bom.csv"
    path.write_text("﻿interaction_id,date\nI001,2026-03-02\n", encoding="utf-8")

    assert read_header(path) == ["interaction_id", "date"]


def test_read_header_on_a_file_with_nothing_in_it_names_no_columns(tmp_path):
    """No `StopIteration` out of `next()` — the CLI needs a false gate, not a traceback."""
    path = tmp_path / "blank.csv"
    path.write_text("", encoding="utf-8")

    assert read_header(path) == []


def test_clean_rows_accepts_an_iterator(as_of):
    """The CLI streams rows; the cleaner must not require a list."""
    rows = (raw_row(interaction_id=f"I{i:03d}") for i in range(3))

    cleaned, report = clean_rows(rows, as_of=as_of)

    assert report.rows_in == 3
    assert len(cleaned) == 3
