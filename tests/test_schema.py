"""The canonical vocabulary the whole pipeline agrees on.

These are not "constants restated" tests: every assertion here catches a typo that
would otherwise make `clean` silently drop real rows.
"""

import pytest

from agenticcoding import schema


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
