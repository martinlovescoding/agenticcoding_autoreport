"""Generate a deliberately dirty multichannel engagement CSV.

The dirt is not random noise — each defect exists because a cleaning stage claims
to handle it, and the counts are chosen so the report's "Data basis" panel has
something true to say. Reproducible: the same seed produces byte-identical output.

Shape of the data (200 rows by default):

* 184 analysable rows spread across Mar–Aug 2026, peaking in May
* 8 duplicate interaction ids, 6 unusable dates, 2 future dates — the 16 drops
* channel and specialty spelling variants, mixed date formats, and a handful of
  value defects (negative/implausible duration, out-of-range score, blank labels)

Engagement is modelled per channel: personal channels score high, broadcast email
scores low. That is the story the report is meant to tell.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import schema

WINDOW_START = dt.date(2026, 3, 1)
WINDOW_END = dt.date(2026, 8, 31)

REPS: tuple[str, ...] = (
    "Anna Weber",
    "Jonas Klein",
    "Miriam Roth",
    "Tobias Lang",
    "Sara Nguyen",
    "Felix Braun",
)

# Share of the window's volume per month — May is the campaign peak.
MONTH_WEIGHTS: dict[int, float] = {3: 30, 4: 27, 5: 45, 6: 34, 7: 23, 8: 25}

# Share of volume per channel. Sums to 1.0.
CHANNEL_WEIGHTS: dict[str, float] = {
    "F2F Call": 0.27,
    "Rep Email": 0.19,
    "HQ Email": 0.15,
    "Phone Call": 0.11,
    "Screen-to-Screen Call": 0.11,
    "Event": 0.09,
    "Web": 0.08,
}

# (mean, sd) of the engagement score per channel — the report's headline finding.
CHANNEL_ENGAGEMENT: dict[str, tuple[float, float]] = {
    "F2F Call": (79.0, 11.0),
    "Phone Call": (63.0, 12.0),
    "Screen-to-Screen Call": (64.0, 12.0),
    "Rep Email": (39.0, 11.0),
    "HQ Email": (24.0, 9.0),
    "Event": (79.0, 10.0),
    "Web": (38.0, 11.0),
}

# (mean, sd) of the duration in minutes per channel.
CHANNEL_DURATION: dict[str, tuple[float, float]] = {
    "F2F Call": (30.0, 7.0),
    "Phone Call": (18.0, 5.0),
    "Screen-to-Screen Call": (25.0, 6.0),
    "Rep Email": (6.0, 3.0),
    "HQ Email": (4.0, 2.0),
    "Event": (75.0, 18.0),
    "Web": (8.0, 4.0),
}

SPECIALTY_WEIGHTS: dict[str, float] = {
    "General Medicine": 0.28,
    "Oncology": 0.22,
    "Cardiology": 0.20,
    "Pulmonology": 0.16,
    "Diabetology": 0.14,
}

# Deliberately misspelled variants the cleaner is expected to absorb.
CHANNEL_VARIANTS: dict[str, tuple[str, ...]] = {
    "F2F Call": ("F2F", "f2f", "face-to-face", "  F2F   Call ", "Visit"),
    "Phone Call": ("Phone", "telephone call", "Telefon", "phone"),
    "Screen-to-Screen Call": ("S2S", "Screen-to-Screen", "video call", "VC"),
    "Rep Email": ("rep-email", "Rep-Email", "R Email", "field email"),
    "HQ Email": ("HQ_Email", "hq", "Headquarters Email", "newsletter"),
    "Event": ("event", "Congress", "Symposium", "Advisory Board"),
    "Web": ("web", "Webinar", "website", "Digital"),
}

SPECIALTY_VARIANTS: dict[str, tuple[str, ...]] = {
    "Oncology": ("Onkologie", "oncology", "Onco", "Haemato-Oncology"),
    "Cardiology": ("Kardiologie", "cardiology", "Cardio"),
    "General Medicine": ("Allgemeinmedizin", "general medicine", "GP", "Allgemeinmed."),
    "Pulmonology": ("Pneumologie", "pulmonology", "Pneumo", "Respiratory"),
    "Diabetology": ("Diabetologie", "diabetology", "Diabetes", "Diabeto"),
}

DATE_FORMATS: tuple[str, ...] = ("%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d")

INVALID_DATES: tuple[str, ...] = ("", "not a date", "2026-13-45", "32.13.2026", "  ", "n/a")

# Probabilities that a given row carries a repairable spelling defect.
CHANNEL_VARIANT_RATE = 0.45
SPECIALTY_VARIANT_RATE = 0.55
DATE_FORMAT_RATE = 0.35

EMAIL_OPEN_RATE = 0.48
EMAIL_CLICK_RATE = 0.63

HCP_POOL_SIZE = 75


def _half_up(value: float) -> int:
    """Round half away from zero — `round()` would give 0 for 0.5 and lose a row."""
    return int(value + 0.5)


def _allocate(total: int, weights: list[float]) -> list[int]:
    """Split `total` across buckets by weight, hitting the total exactly."""
    if total <= 0:
        return [0] * len(weights)
    share = sum(weights)
    if share <= 0:
        return [0] * len(weights)
    exact = [total * weight / share for weight in weights]
    counts = [int(value) for value in exact]
    remainder = total - sum(counts)
    order = sorted(range(len(weights)), key=lambda i: exact[i] - counts[i], reverse=True)
    for index in order[:remainder]:
        counts[index] += 1
    return counts


def _pick(rng: random.Random, weights: Mapping[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _month_dates(year: int, month: int, count: int, rng: random.Random) -> list[dt.date]:
    """`count` dates inside one month, without needing to know the month length."""
    first = dt.date(year, month, 1)
    next_month = dt.date(year + (month == 12), month % 12 + 1, 1)
    span = (next_month - first).days
    return [first + dt.timedelta(days=rng.randrange(span)) for _ in range(count)]


def _format_date(day: dt.date, rng: random.Random) -> str:
    if rng.random() < DATE_FORMAT_RATE:
        return day.strftime(rng.choice(DATE_FORMATS))
    return day.isoformat()


def generate(rows: int = 200, *, seed: int = 7) -> list[dict[str, str]]:
    """Build `rows` raw CSV rows, `rows` of which are deliberately defective."""
    if rows < 1:
        raise ValueError("rows must be at least 1")

    rng = random.Random(seed)

    duplicates = _half_up(rows * 0.04)
    invalid_dates = _half_up(rows * 0.03)
    future_dates = _half_up(rows * 0.01)
    analysable = max(0, rows - duplicates - invalid_dates - future_dates)

    # --- the analysable core -------------------------------------------------
    months = sorted(MONTH_WEIGHTS)
    per_month = _allocate(analysable, [MONTH_WEIGHTS[month] for month in months])

    records: list[dict[str, str]] = []
    for month, count in zip(months, per_month):
        for day in _month_dates(WINDOW_START.year, month, count, rng):
            channel = _pick(rng, CHANNEL_WEIGHTS)
            records.append(_build_record(rng, day, channel, len(records)))

    _apply_value_defects(records, rows, rng)
    _apply_spelling_defects(records, rng)

    # --- the deliberate drops ------------------------------------------------
    hcp_pool = [f"H{index:03d}" for index in range(1, HCP_POOL_SIZE + 1)]
    for offset in range(duplicates):
        clone = dict(records[offset % len(records)])
        clone["engagement_score"] = str(_half_up(rng.uniform(10, 90)))
        records.append(clone)

    for offset in range(invalid_dates):
        records.append(
            _build_record(
                rng,
                WINDOW_START + dt.timedelta(days=offset),
                _pick(rng, CHANNEL_WEIGHTS),
                len(records) + 1000,
                date_text=rng.choice(INVALID_DATES),
                hcp_pool=hcp_pool,
            )
        )

    for offset in range(future_dates):
        future = WINDOW_END + dt.timedelta(days=30 + offset * 17)
        records.append(
            _build_record(
                rng,
                future,
                _pick(rng, CHANNEL_WEIGHTS),
                len(records) + 2000,
                hcp_pool=hcp_pool,
            )
        )

    # `rows` is the contract; trimming guards against an arithmetic slip.
    return records[:rows] if len(records) > rows else records


def _build_record(
    rng: random.Random,
    day: dt.date,
    channel: str,
    index: int,
    *,
    date_text: str | None = None,
    hcp_pool: list[str] | None = None,
) -> dict[str, str]:
    mean, sd = CHANNEL_ENGAGEMENT[channel]
    score = min(100.0, max(0.0, rng.gauss(mean, sd)))
    duration = max(1, _half_up(rng.gauss(*CHANNEL_DURATION[channel])))

    pool = hcp_pool or [f"H{number:03d}" for number in range(1, HCP_POOL_SIZE + 1)]
    hcp_id = rng.choice(pool)

    opened = clicked = ""
    if channel in schema.EMAIL_CHANNELS:
        was_opened = rng.random() < EMAIL_OPEN_RATE
        opened = "Y" if was_opened else "N"
        clicked = "Y" if was_opened and rng.random() < EMAIL_CLICK_RATE else "N"

    return {
        "interaction_id": f"I{index + 1:04d}",
        "date": date_text if date_text is not None else _format_date(day, rng),
        "rep_name": rng.choice(REPS),
        "hcp_id": hcp_id,
        "specialty": _pick(rng, SPECIALTY_WEIGHTS),
        "channel": channel,
        "product": rng.choice(schema.PRODUCTS),
        "duration_min": str(duration),
        "engagement_score": f"{score:.1f}",
        "opened": opened,
        "clicked": clicked,
    }


def _apply_value_defects(
    records: list[dict[str, str]], rows: int, rng: random.Random
) -> None:
    """Sprinkle the value defects the cleaner repairs, on disjoint rows."""
    plan = [
        ("duration_min", lambda: str(-rng.randint(5, 45)), _half_up(rows * 0.01)),
        ("duration_min", lambda: str(rng.randint(600, 2400)), _half_up(rows * 0.01)),
        ("engagement_score", lambda: f"{rng.uniform(101, 180):.1f}", _half_up(rows * 0.01)),
        ("product", lambda: rng.choice(["", "  ", "n/a"]), _half_up(rows * 0.03)),
        ("rep_name", lambda: rng.choice(["", "  ", "n/a"]), _half_up(rows * 0.01)),
        ("engagement_score", lambda: "", _half_up(rows * 0.025)),
    ]
    wanted = sum(count for _, _, count in plan)
    if wanted == 0 or not records:
        return

    targets = rng.sample(range(len(records)), min(wanted, len(records)))
    cursor = 0
    for field, make_value, count in plan:
        for _ in range(count):
            if cursor >= len(targets):
                return
            records[targets[cursor]][field] = make_value()
            cursor += 1


def _apply_spelling_defects(records: list[dict[str, str]], rng: random.Random) -> None:
    """Rewrite some channels and specialties into the spellings `clean` must absorb."""
    for record in records:
        if rng.random() < CHANNEL_VARIANT_RATE:
            record["channel"] = rng.choice(CHANNEL_VARIANTS[record["channel"]])
        if rng.random() < SPECIALTY_VARIANT_RATE:
            record["specialty"] = rng.choice(SPECIALTY_VARIANTS[record["specialty"]])


def write_raw(rows: Iterable[Mapping[str, str]], path: str | Path) -> None:
    """Write raw rows as UTF-8 CSV with the canonical header order."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(schema.RAW_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
