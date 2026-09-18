"""The canonical vocabulary the whole pipeline agrees on.

These are not "constants restated" tests: every assertion here catches a typo that
would otherwise make `clean` silently drop real rows.
"""

import datetime as dt

import pytest

from agenticcoding import schema
from conftest import interaction


def test_seven_canonical_channels_in_report_order():
    assert schema.CHANNELS == (
        "F2F Call",
        "Phone Call",
        "Screen-to-Screen Call",
        "Rep Email",
        "HQ Email",
        "Event",
        "Web",
    )


def test_every_channel_has_a_short_label():
    assert set(schema.CHANNEL_SHORT) == set(schema.CHANNELS)


def test_every_synonym_maps_to_a_canonical_channel():
    for key, target in schema.CHANNEL_SYNONYMS.items():
        assert target in schema.CHANNELS, f"{key!r} maps to unknown channel {target!r}"


def test_every_channel_maps_to_itself():
    """Without the self-mapping, already-clean rows would be dropped as unmappable."""
    for channel in schema.CHANNELS:
        key = schema.normalize_key(channel)
        assert schema.CHANNEL_SYNONYMS.get(key) == channel, f"{channel!r} is not self-mapped"


def test_synonym_keys_are_already_normalized():
    """Keys must be in normalized form, or a lookup would never reach them."""
    for key in schema.CHANNEL_SYNONYMS:
        assert schema.normalize_key(key) == key, f"{key!r} is not a normalized key"


def test_every_specialty_has_a_short_label():
    assert set(schema.SPECIALTY_SHORT) == set(schema.SPECIALTIES)


def test_every_specialty_synonym_maps_to_a_canonical_specialty():
    for key, target in schema.SPECIALTY_SYNONYMS.items():
        assert target in schema.SPECIALTIES, f"{key!r} maps to unknown specialty {target!r}"


def test_every_specialty_maps_to_itself():
    for specialty in schema.SPECIALTIES:
        key = schema.normalize_key(specialty)
        assert schema.SPECIALTY_SYNONYMS.get(key) == specialty, f"{specialty!r} not self-mapped"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("F2F Call", "f2fcall"),
        ("  f2f   call ", "f2fcall"),
        ("Screen-to-Screen Call", "screentoscreencall"),
        ("Rep-Email", "repemail"),
        ("HQ_Email", "hqemail"),
        ("Onkologie", "onkologie"),
        ("Allgemeinmedizin", "allgemeinmedizin"),
        ("", ""),
    ],
)
def test_normalize_key_collapses_case_whitespace_and_punctuation(raw, expected):
    assert schema.normalize_key(raw) == expected


def test_email_channels_are_the_two_email_ones():
    assert set(schema.EMAIL_CHANNELS) == {"Rep Email", "HQ Email"}
    for channel in schema.EMAIL_CHANNELS:
        assert channel in schema.CHANNELS


def test_bounds_are_sane():
    low, high = schema.ENGAGEMENT_RANGE
    assert (low, high) == (0, 100)
    assert schema.DURATION_MAX_PLAUSIBLE == 300


# --- the German display vocabulary --------------------------------------------


def test_the_canonical_names_stay_english_keys():
    """The canonical names are *keys*, not display text.

    `SPECIALTY_SYNONYMS` matches against them and `test_clean.py` pins them, so the
    German a reader sees comes from a display map at the render boundary instead.
    Renaming them here would drag `conftest.py` and five test files with it.
    """
    assert schema.SPECIALTIES == (
        "Oncology",
        "Cardiology",
        "General Medicine",
        "Pulmonology",
        "Diabetology",
    )


def test_every_specialty_has_a_german_display_label():
    assert set(schema.SPECIALTY_LABELS) == set(schema.SPECIALTIES)


def test_the_display_label_of_an_unknown_specialty_is_its_own_name():
    """The cleaner keeps unrecognized specialties verbatim, so they still appear."""
    assert schema.specialty_label("Onkologie aus Freitext") == "Onkologie aus Freitext"


def test_a_known_specialty_displays_in_german():
    assert schema.specialty_label("General Medicine") == "Allgemeinmedizin"


@pytest.mark.parametrize(
    ("month", "short", "long"),
    [
        (1, "Jan", "Januar"),
        (3, "Mär", "März"),
        (5, "Mai", "Mai"),
        (8, "Aug", "August"),
        (12, "Dez", "Dezember"),
    ],
)
def test_month_labels_are_german(month, short, long):
    row = interaction(date=dt.date(2026, month, 2))

    assert row.month_label == short
    assert row.month_label_full == f"{short} 2026"
    assert schema.MONTHS_LONG[month - 1] == long


def test_month_labels_do_not_come_from_the_system_locale():
    """`strftime("%b")` resolves against `LC_TIME`, so the page would render
    differently on a German machine than on an English one — and the same CSV would
    produce two different reports. The table is the only source.
    """
    for month in range(1, 13):
        row = interaction(date=dt.date(2026, month, 15))

        assert row.month_label == schema.MONTHS_SHORT[month - 1]
