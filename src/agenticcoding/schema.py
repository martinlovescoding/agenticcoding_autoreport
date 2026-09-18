"""Canonical vocabulary shared by the generator, the cleaner and the report.

Everything downstream of cleaning speaks these seven channels and these five
specialties. Synonyms live here so `clean` never has to guess, and so the
generator can produce exactly the dirt the cleaner is built to absorb.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

# --- channels ---------------------------------------------------------------

CHANNELS: tuple[str, ...] = (
    "F2F Call",
    "Phone Call",
    "Screen-to-Screen Call",
    "Rep Email",
    "HQ Email",
    "Event",
    "Web",
)

CHANNEL_SHORT: dict[str, str] = {
    "F2F Call": "F2F",
    "Phone Call": "Phone",
    "Screen-to-Screen Call": "S2S",
    "Rep Email": "Rep Email",
    "HQ Email": "HQ Email",
    "Event": "Event",
    "Web": "Web",
}

EMAIL_CHANNELS: tuple[str, ...] = ("Rep Email", "HQ Email")

# Keys are normalized (see `normalize_key`), values are canonical channels.
CHANNEL_SYNONYMS: dict[str, str] = {
    # F2F
    "f2fcall": "F2F Call",
    "f2f": "F2F Call",
    "facetoface": "F2F Call",
    "facetofacecall": "F2F Call",
    "visit": "F2F Call",
    "inperson": "F2F Call",
    "callf2f": "F2F Call",
    "persoenlich": "F2F Call",
    # Phone
    "phonecall": "Phone Call",
    "phone": "Phone Call",
    "telephonecall": "Phone Call",
    "telefon": "Phone Call",
    "call": "Phone Call",
    "remotecall": "Phone Call",
    # Screen-to-Screen
    "screentoscreencall": "Screen-to-Screen Call",
    "screentoscreen": "Screen-to-Screen Call",
    "s2s": "Screen-to-Screen Call",
    "s2scall": "Screen-to-Screen Call",
    "videocall": "Screen-to-Screen Call",
    "vc": "Screen-to-Screen Call",
    "screenshare": "Screen-to-Screen Call",
    # Rep Email
    "repemail": "Rep Email",
    "remail": "Rep Email",
    "salesrepemail": "Rep Email",
    "fieldemail": "Rep Email",
    # HQ Email
    "hqemail": "HQ Email",
    "hq": "HQ Email",
    "headquartersemail": "HQ Email",
    "centralemail": "HQ Email",
    "newsletter": "HQ Email",
    # Event
    "event": "Event",
    "events": "Event",
    "congress": "Event",
    "symposium": "Event",
    "advisoryboard": "Event",
    "fachtagung": "Event",
    # Web
    "web": "Web",
    "webinar": "Web",
    "website": "Web",
    "webvisit": "Web",
    "digital": "Web",
    "online": "Web",
    "portal": "Web",
}

# --- specialties ------------------------------------------------------------

SPECIALTIES: tuple[str, ...] = (
    "Oncology",
    "Cardiology",
    "General Medicine",
    "Pulmonology",
    "Diabetology",
)

SPECIALTY_SHORT: dict[str, str] = {
    "Oncology": "Oncology",
    "Cardiology": "Cardiology",
    "General Medicine": "General Med.",
    "Pulmonology": "Pulmonology",
    "Diabetology": "Diabetology",
}

# What a reader sees. The canonical names above are *keys*: `SPECIALTY_SYNONYMS`
# matches against them and the tests pin them, so translating them in place would
# drag the synonym tables, the fixtures and five test files along with it. This map
# is applied at the render boundary instead — `metrics.specialty_matrix` copies the
# label onto each row, exactly as `MonthStat.label` already does for months.
SPECIALTY_LABELS: dict[str, str] = {
    "Oncology": "Onkologie",
    "Cardiology": "Kardiologie",
    "General Medicine": "Allgemeinmedizin",
    "Pulmonology": "Pneumologie",
    "Diabetology": "Diabetologie",
}


def specialty_label(specialty: str) -> str:
    """The German name for a specialty, or the name itself if it is unrecognized.

    The cleaner keeps an unknown specialty verbatim rather than dropping the row, so
    a report can legitimately carry a label that is not in `SPECIALTIES`. Showing it
    untranslated is right; showing it as a blank or a placeholder would not be.
    """
    return SPECIALTY_LABELS.get(specialty, specialty)


# --- months -------------------------------------------------------------------

# Explicit tables, never `strftime("%b")`. `%b` resolves against the process locale,
# so a report generated on a German machine and one generated on an English machine
# would carry different month names from the same CSV — and "same input, same bytes"
# is one of the system's standing promises.
MONTHS_SHORT: tuple[str, ...] = (
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
)

MONTHS_LONG: tuple[str, ...] = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)

SPECIALTY_SYNONYMS: dict[str, str] = {
    "oncology": "Oncology",
    "onkologie": "Oncology",
    "onco": "Oncology",
    "haematooncology": "Oncology",
    "haematology": "Oncology",
    "cardiology": "Cardiology",
    "kardiologie": "Cardiology",
    "cardio": "Cardiology",
    "generalmedicine": "General Medicine",
    "allgemeinmedizin": "General Medicine",
    "allgemeinmed": "General Medicine",
    "generalpractice": "General Medicine",
    "gp": "General Medicine",
    "hausarzt": "General Medicine",
    "pulmonology": "Pulmonology",
    "pneumologie": "Pulmonology",
    "pneumo": "Pulmonology",
    "respiratory": "Pulmonology",
    "lunge": "Pulmonology",
    "diabetology": "Diabetology",
    "diabetologie": "Diabetology",
    "diabetes": "Diabetology",
    "diabeto": "Diabetology",
    "endokrinologie": "Diabetology",
}

# --- value bounds -----------------------------------------------------------

ENGAGEMENT_RANGE: tuple[int, int] = (0, 100)
DURATION_MAX_PLAUSIBLE: int = 300

# These two are written *into* the cleaned CSV rather than matched against, so unlike
# the channel and specialty names they are values a reader sees. The data-basis panel
# names them ("Fehlendes Produkt → …"), and a label has to name what the pipeline
# actually wrote, so the values are German and the labels are built from these.
UNKNOWN_PRODUCT: str = "Unbekannt"
UNKNOWN_REP: str = "Nicht zugeordnet"

PRODUCTS: tuple[str, ...] = ("Zorvex", "Nevastin", "Cardilux", "Pulmofix")

# --- raw CSV shape ----------------------------------------------------------

RAW_COLUMNS: tuple[str, ...] = (
    "interaction_id",
    "date",
    "rep_name",
    "hcp_id",
    "specialty",
    "channel",
    "product",
    "duration_min",
    "engagement_score",
    "opened",
    "clicked",
)


def normalize_key(text: str) -> str:
    """Collapse a human label to a lookup key: lowercase, letters and digits only.

    ``"Screen-to-Screen Call"`` and ``"screen to screen call"`` both become
    ``"screentoScreencall"``, so a synonym table needs one entry per spelling
    rather than one per punctuation variant.
    """
    return re.sub(r"[^a-z0-9]+", "", text.strip().lower())


# --- the cleaned row --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Interaction:
    """One cleaned interaction — the only shape the metrics layer ever sees."""

    interaction_id: str
    date: _dt.date
    rep_name: str
    hcp_id: str
    specialty: str
    channel: str
    product: str
    duration_min: int | None
    engagement_score: float | None
    opened: bool | None
    clicked: bool | None

    @property
    def month(self) -> str:
        """Sortable month key, e.g. ``"2026-03"``."""
        return f"{self.date.year:04d}-{self.date.month:02d}"

    @property
    def month_label(self) -> str:
        """Three-letter month label for an axis, e.g. ``"Mär"``."""
        return MONTHS_SHORT[self.date.month - 1]

    @property
    def month_label_full(self) -> str:
        """Month and year, for a table row: ``"Mär 2026"``."""
        return f"{self.month_label} {self.date.year}"
