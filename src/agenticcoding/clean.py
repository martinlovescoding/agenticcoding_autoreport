"""Turn a dirty CSV into `Interaction` rows, and report what had to be fixed.

The pipeline is a single ordered pass over the raw rows. Every stage that changes
something increments a counter, and those counters are what the report's "Data
basis" panel shows — so the report can never quietly drop data.

Two deliberate policies:

* **Values are repaired, not discarded.** A score of 140 is clamped to 100 and a
  duration of -12 min is read as 12; both are transcription slips, and dropping
  the row would cost real volume. The repair is counted and shown.
* **Rows are only dropped when they cannot be attributed at all** — no id, an
  unrecognized channel, or a date that is missing, unparseable or in the future.

Unrecognized *specialties* are kept verbatim rather than dropped: they are a
label, and a stray label is better shown than silently deleted.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from . import schema
from .schema import Interaction

# --- text helpers -----------------------------------------------------------

_HEADER_SEPARATORS = re.compile(r"[\s_\-]+")
_WHITESPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

_MISSING = frozenset({"", "-", "--", "n/a", "na", "none", "null", "unknown", "?"})
# Labels get their own set: "unknown" is a missing-marker for a *number* but it is
# also the sentinel we write for a missing product, so counting it as missing would
# make a second cleaning pass re-count our own output.
_LABEL_MISSING = frozenset({"", "-", "--", "n/a", "na", "none", "null", "?"})
_TRUE = frozenset({"y", "yes", "1", "true", "t", "ja"})
_FALSE = frozenset({"n", "no", "0", "false", "f", "nein"})

# Order matters for ambiguous slash dates: month-first wins, documented in the README.
_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d")


def _text(value: object) -> str:
    """Trim a raw cell: NBSP to space, strip ends, collapse inner runs."""
    return _WHITESPACE.sub(" ", str(value).replace("\xa0", " ")).strip()


def _number(value: object) -> float | None:
    """Pull a number out of a cell like ``"45 min"`` or ``"56,3"``."""
    raw = _text(value)
    if raw.lower() in _MISSING:
        return None
    match = _NUMBER.search(raw.replace(" ", ""))
    if match is None:
        return None
    return float(match.group(0).replace(",", "."))


def _integer(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(round(number))


def _flag(value: object) -> bool | None:
    raw = _text(value).lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return None


def _parse_date(value: object) -> dt.date | None:
    raw = _text(value)
    if raw.lower() in _MISSING:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_headers(row: Mapping[str, object]) -> dict[str, str]:
    """``" Duration_Min "`` and ``"duration-min"`` both become ``"duration_min"``."""
    return {
        _HEADER_SEPARATORS.sub("_", str(key).strip().lower()): _text(value)
        for key, value in row.items()
        if key is not None
    }


# --- the quality report -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class QualityNote:
    """One cleaning stage and how many rows it touched."""

    key: str
    label: str
    count: int


# Every stage, in pipeline order. All of them are always reported, even at zero,
# so the report's quality table has a stable shape.
_STAGE_LABELS: tuple[tuple[str, str], ...] = (
    ("duplicates", "Duplicate interaction_id rows removed"),
    ("id_missing", "Rows with a missing interaction_id removed"),
    ("channels", "Channel names normalized (variants → 7 channels)"),
    ("unknown_channel", "Rows with an unrecognized channel removed"),
    ("specialties", "Specialty spellings unified"),
    ("dates_invalid", "Rows with a missing or invalid date removed"),
    ("dates_future", "Rows with a date in the future removed"),
    ("duration_negative", "Negative duration corrected (absolute value)"),
    ("duration_implausible", "Implausible duration (> 300 min) set to missing"),
    ("engagement_clamped", "Engagement score clamped to 0–100"),
    ("product_missing", "Missing product → 'Unknown'"),
    ("rep_missing", "Missing rep name → 'Unassigned'"),
)


@dataclass(frozen=True, slots=True)
class QualityReport:
    """What the pipeline did, in numbers the report can show verbatim."""

    rows_in: int
    rows_out: int
    notes: tuple[QualityNote, ...]

    def count(self, key: str) -> int:
        for note in self.notes:
            if note.key == key:
                return note.count
        raise KeyError(key)

    @property
    def analyzable_share(self) -> float:
        """Share of raw rows that survived, in percent."""
        if self.rows_in == 0:
            return 0.0
        return 100.0 * self.rows_out / self.rows_in


# --- the pipeline -----------------------------------------------------------


def clean_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    as_of: dt.date | None = None,
) -> tuple[list[Interaction], QualityReport]:
    """Clean raw CSV rows. Returns the surviving rows and a `QualityReport`.

    `as_of` is the reference date for the "future date" rule; it is injected
    rather than read from the clock so the pipeline stays deterministic.
    """
    today = as_of or dt.date.today()
    counts: Counter[str] = Counter()

    raw_rows = [_normalize_headers(row) for row in rows]
    counts["rows_in"] = len(raw_rows)

    # 1. identity — duplicates and unusable ids first, so every later counter
    #    counts rows that actually reach that stage.
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for row in raw_rows:
        interaction_id = row.get("interaction_id", "")
        if not interaction_id:
            counts["id_missing"] += 1
            continue
        if interaction_id in seen:
            counts["duplicates"] += 1
            continue
        seen.add(interaction_id)
        unique.append(row)

    cleaned: list[Interaction] = []
    for row in unique:
        # 2. channel — an unrecognized channel makes the row unattributable.
        raw_channel = row.get("channel", "")
        channel = schema.CHANNEL_SYNONYMS.get(schema.normalize_key(raw_channel))
        if channel is None:
            counts["unknown_channel"] += 1
            continue
        if channel != raw_channel:
            counts["channels"] += 1

        # 3. specialty — a label, so an unrecognized one is kept rather than dropped.
        raw_specialty = row.get("specialty", "")
        specialty = schema.SPECIALTY_SYNONYMS.get(schema.normalize_key(raw_specialty), raw_specialty)
        if specialty != raw_specialty:
            counts["specialties"] += 1

        # 4. date
        date = _parse_date(row.get("date", ""))
        if date is None:
            counts["dates_invalid"] += 1
            continue
        if date > today:
            counts["dates_future"] += 1
            continue

        # 5. duration
        duration = _integer(row.get("duration_min", ""))
        if duration is not None and duration < 0:
            counts["duration_negative"] += 1
            duration = abs(duration)
        if duration is not None and duration > schema.DURATION_MAX_PLAUSIBLE:
            counts["duration_implausible"] += 1
            duration = None

        # 6. engagement score
        low, high = schema.ENGAGEMENT_RANGE
        score = _number(row.get("engagement_score", ""))
        if score is not None and not (low <= score <= high):
            counts["engagement_clamped"] += 1
            score = min(max(score, float(low)), float(high))

        # 7. labels
        product = row.get("product", "")
        if product.lower() in _LABEL_MISSING:
            counts["product_missing"] += 1
            product = schema.UNKNOWN_PRODUCT

        rep_name = row.get("rep_name", "")
        if rep_name.lower() in _LABEL_MISSING:
            counts["rep_missing"] += 1
            rep_name = schema.UNKNOWN_REP

        cleaned.append(
            Interaction(
                interaction_id=row["interaction_id"],
                date=date,
                rep_name=rep_name,
                hcp_id=row.get("hcp_id", ""),
                specialty=specialty,
                channel=channel,
                product=product,
                duration_min=duration,
                engagement_score=score,
                opened=_flag(row.get("opened", "")),
                clicked=_flag(row.get("clicked", "")),
            )
        )

    # Stable order makes the output byte-deterministic for golden tests.
    cleaned.sort(key=lambda row: (row.date, row.interaction_id))

    notes = tuple(
        QualityNote(key=key, label=label, count=counts[key]) for key, label in _STAGE_LABELS
    )
    return cleaned, QualityReport(rows_in=counts["rows_in"], rows_out=len(cleaned), notes=notes)


# --- csv I/O ----------------------------------------------------------------


def read_csv(path: str | Path) -> list[dict[str, str]]:
    """Read raw rows. ``utf-8-sig`` so a BOM from Excel does not corrupt the first header."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def write_csv(rows: Iterable[Interaction], path: str | Path) -> None:
    """Write cleaned rows so they can be re-read by `read_csv` unchanged."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(schema.RAW_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _cell(getattr(row, column)) for column in schema.RAW_COLUMNS})


def iter_csv(path: str | Path) -> Iterator[dict[str, str]]:
    """Stream raw rows without holding the whole file in memory."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)
