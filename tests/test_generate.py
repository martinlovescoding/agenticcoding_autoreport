"""The synthetic data source.

The generator's job is not just "some rows" — it must produce *exactly* the dirt
the cleaner claims to handle, or the cleaning tests are vacuous. The dirt-presence
tests below are the load-bearing ones.
"""

import csv
import datetime as dt

import pytest

from agenticcoding import schema
from agenticcoding.clean import clean_rows
from agenticcoding.generate import generate, write_raw
from conftest import AS_OF

WINDOW_START = dt.date(2026, 3, 1)
WINDOW_END = dt.date(2026, 8, 31)


def parse_date(text: str) -> dt.date | None:
    """Parse a raw date cell the way the generator emits them."""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def as_number(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


# --- shape --------------------------------------------------------------------


def test_generates_the_requested_number_of_rows():
    assert len(generate(200, seed=1)) == 200


def test_row_count_scales_down():
    assert len(generate(50, seed=1)) == 50


def test_header_matches_the_raw_column_contract(tmp_path):
    path = tmp_path / "raw.csv"
    write_raw(generate(20, seed=1), path)

    with open(path, newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))

    assert header == list(schema.RAW_COLUMNS)


def test_every_row_carries_every_column():
    for row in generate(50, seed=1):
        assert set(row) == set(schema.RAW_COLUMNS)


# --- determinism --------------------------------------------------------------


def test_same_seed_produces_identical_bytes(tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"

    write_raw(generate(200, seed=7), first)
    write_raw(generate(200, seed=7), second)

    assert first.read_bytes() == second.read_bytes()


def test_different_seed_produces_different_data():
    assert generate(200, seed=7) != generate(200, seed=8)


# --- coverage: the report needs every channel and specialty -------------------


def test_cleaning_the_generated_data_yields_every_channel():
    cleaned, _ = clean_rows(generate(200, seed=7), as_of=AS_OF)

    assert {row.channel for row in cleaned} == set(schema.CHANNELS)


def test_cleaning_the_generated_data_yields_every_specialty():
    cleaned, _ = clean_rows(generate(200, seed=7), as_of=AS_OF)

    assert {row.specialty for row in cleaned} == set(schema.SPECIALTIES)


def test_the_window_covers_every_month_from_march_to_august():
    cleaned, _ = clean_rows(generate(200, seed=7), as_of=AS_OF)

    assert sorted({row.month for row in cleaned}) == [
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
    ]


def test_most_rows_land_inside_the_window():
    rows = generate(200, seed=7)
    inside = [
        row
        for row in rows
        if (parsed := parse_date(row["date"])) is not None and WINDOW_START <= parsed <= WINDOW_END
    ]

    assert len(inside) > 170


# --- dirt presence: these guarantee the cleaning tests are not vacuous --------


@pytest.fixture(scope="module")
def raw_rows() -> list[dict[str, str]]:
    return generate(200, seed=7)


def test_produces_non_canonical_channel_spellings(raw_rows):
    variants = [row for row in raw_rows if row["channel"].strip() not in schema.CHANNELS]

    assert len(variants) > 20, "the channel normalizer needs real work to do"


def test_produces_non_canonical_specialty_spellings(raw_rows):
    variants = [row for row in raw_rows if row["specialty"].strip() not in schema.SPECIALTIES]

    assert len(variants) > 20, "the specialty normalizer needs real work to do"


def test_produces_duplicate_interaction_ids(raw_rows):
    ids = [row["interaction_id"] for row in raw_rows]

    assert len(ids) > len(set(ids)), "duplicate ids are a cleaning stage"


def test_produces_more_than_one_date_format(raw_rows):
    formats = {
        fmt
        for row in raw_rows
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d")
        if _matches(row["date"], fmt)
    }

    assert len(formats) >= 2


def test_produces_unparseable_dates(raw_rows):
    assert any(parse_date(row["date"]) is None for row in raw_rows)


def test_produces_future_dates(raw_rows):
    assert any(
        (parsed := parse_date(row["date"])) is not None and parsed > AS_OF for row in raw_rows
    )


def test_produces_negative_durations(raw_rows):
    assert any((value := as_number(row["duration_min"])) is not None and value < 0 for row in raw_rows)


def test_produces_implausible_durations(raw_rows):
    assert any(
        (value := as_number(row["duration_min"])) is not None
        and value > schema.DURATION_MAX_PLAUSIBLE
        for row in raw_rows
    )


def test_produces_out_of_range_engagement_scores(raw_rows):
    low, high = schema.ENGAGEMENT_RANGE
    assert any(
        (value := as_number(row["engagement_score"])) is not None and not (low <= value <= high)
        for row in raw_rows
    )


def test_produces_missing_products(raw_rows):
    assert any(not row["product"].strip() for row in raw_rows)


def test_produces_missing_rep_names(raw_rows):
    assert any(not row["rep_name"].strip() for row in raw_rows)


def test_produces_missing_engagement_scores(raw_rows):
    assert any(not row["engagement_score"].strip() for row in raw_rows)


# --- the generator and the cleaner agree --------------------------------------


def test_cleaning_keeps_all_rows_but_the_deliberate_drops(raw_rows):
    cleaned, report = clean_rows(raw_rows, as_of=AS_OF)

    assert report.rows_in == 200
    assert report.rows_out == len(cleaned) == 184
    assert report.count("unknown_channel") == 0, "the generator must not invent foreign channels"
    assert report.count("id_missing") == 0


def test_the_deliberate_drops_are_the_documented_ones(raw_rows):
    _, report = clean_rows(raw_rows, as_of=AS_OF)

    assert report.count("duplicates") == 8
    assert report.count("dates_invalid") == 6
    assert report.count("dates_future") == 2


def test_every_repair_stage_fires(raw_rows):
    _, report = clean_rows(raw_rows, as_of=AS_OF)

    for key in (
        "channels",
        "specialties",
        "duration_negative",
        "duration_implausible",
        "engagement_clamped",
        "product_missing",
        "rep_missing",
    ):
        assert report.count(key) > 0, f"stage {key!r} never fires on generated data"


def _matches(text: str, fmt: str) -> bool:
    try:
        dt.datetime.strptime(text.strip(), fmt)
    except ValueError:
        return False
    return True
