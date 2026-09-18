"""Shared fixtures.

`raw_row` builds a *valid* raw CSV row; every test overrides exactly the field it
is about. That keeps each test to one behaviour and makes the quality counters
hand-checkable.
"""

import datetime as dt

import pytest

from agenticcoding import schema

# Fixed "as of" date so "future date" is deterministic. The data window is
# Mar–Aug 2026; anything after this is in the future.
AS_OF = dt.date(2026, 9, 18)


def raw_row(**overrides: str) -> dict[str, str]:
    """A clean, valid raw row. Override a field to inject one specific defect."""
    row = {
        "interaction_id": "I001",
        "date": "2026-03-02",
        "rep_name": "Alice",
        "hcp_id": "H001",
        "specialty": "Oncology",
        "channel": "F2F Call",
        "product": "Zorvex",
        "duration_min": "30",
        "engagement_score": "80",
        "opened": "Y",
        "clicked": "N",
    }
    row.update(overrides)
    return row


@pytest.fixture
def as_of() -> dt.date:
    return AS_OF


# --- a tiny hand-computable dataset -------------------------------------------
#
# Eight interactions, chosen so every expected value below can be checked by hand:
#   F2F Call   I1 80, I2 60, I4 70            -> n=3, avg 70.0, 2 HCPs
#   Rep Email  I3 40, I5 20, I6 30            -> n=3, avg 30.0, 2 HCPs
#   Web        I7 50, I8 None                 -> n=2, avg 50.0, 1 HCP
#   email opens: I3 Y, I5 Y, I6 N             -> 2/3 = 66.7%
#   email clicks on opens: I3 Y, I5 N         -> 1/2 = 50.0%
#   overall avg over the 7 non-null scores    -> 350/7 = 50.0


def interaction(**overrides) -> schema.Interaction:
    """A cleaned row. Override a field to place it in a different bucket."""
    fields = {
        "interaction_id": "I001",
        "date": dt.date(2026, 3, 2),
        "rep_name": "Alice",
        "hcp_id": "H001",
        "specialty": "Oncology",
        "channel": "F2F Call",
        "product": "Zorvex",
        "duration_min": 30,
        "engagement_score": 80.0,
        "opened": None,
        "clicked": None,
    }
    fields.update(overrides)
    return schema.Interaction(**fields)


SAMPLE: tuple[schema.Interaction, ...] = (
    interaction(interaction_id="I1", date=dt.date(2026, 3, 5), hcp_id="H1", engagement_score=80.0),
    interaction(interaction_id="I2", date=dt.date(2026, 3, 12), hcp_id="H1", engagement_score=60.0),
    interaction(
        interaction_id="I3",
        date=dt.date(2026, 3, 20),
        hcp_id="H2",
        channel="Rep Email",
        engagement_score=40.0,
        duration_min=5,
        opened=True,
        clicked=True,
    ),
    interaction(
        interaction_id="I4",
        date=dt.date(2026, 4, 2),
        hcp_id="H2",
        specialty="Cardiology",
        engagement_score=70.0,
    ),
    interaction(
        interaction_id="I5",
        date=dt.date(2026, 4, 15),
        hcp_id="H3",
        specialty="Cardiology",
        channel="Rep Email",
        engagement_score=20.0,
        duration_min=4,
        opened=True,
        clicked=False,
    ),
    interaction(
        interaction_id="I6",
        date=dt.date(2026, 4, 28),
        hcp_id="H3",
        specialty="Cardiology",
        channel="Rep Email",
        engagement_score=30.0,
        duration_min=6,
        opened=False,
        clicked=False,
    ),
    interaction(
        interaction_id="I7",
        date=dt.date(2026, 5, 4),
        hcp_id="H4",
        channel="Web",
        engagement_score=50.0,
        duration_min=10,
    ),
    interaction(
        interaction_id="I8",
        date=dt.date(2026, 5, 19),
        hcp_id="H4",
        channel="Web",
        engagement_score=None,
        duration_min=None,
    ),
)


@pytest.fixture
def sample() -> tuple[schema.Interaction, ...]:
    return SAMPLE
