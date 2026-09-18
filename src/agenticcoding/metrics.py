"""The three analyses and the KPI block.

Each function takes cleaned `Interaction` rows and returns a frozen dataclass that
carries *numbers only* — no labels, no colours, no HTML. The template owns all
presentation, so these values can be unit-tested by hand and re-used by any design.

Two rules hold everywhere:

* **Missing values are excluded, never imputed.** A row with no engagement score
  still counts toward volume; it just does not enter an average.
* **Order is deterministic.** Rows follow the canonical `schema` order so a chart
  legend and a table can never disagree about what comes first.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from . import schema
from .schema import Interaction


def _mean(values: Iterable[float | None]) -> float | None:
    """Mean of the present values, or `None` when there are none."""
    present = [value for value in values if value is not None]
    if not present:
        return None
    return statistics.fmean(present)


def _ordered(present: set[str], canonical: Sequence[str]) -> tuple[str, ...]:
    """Canonical order first, then anything unrecognized, alphabetically.

    The cleaner keeps unknown *specialties* verbatim, so a report can legitimately
    contain a label that is not in `schema`; it must still be shown, not dropped.
    """
    known = [value for value in canonical if value in present]
    extra = sorted(present - set(canonical))
    return tuple(known + extra)


# --- 1. channel mix -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChannelStat:
    """One channel's volume, reach and engagement."""

    channel: str
    interactions: int
    hcps: int
    avg_engagement: float | None
    share: float


@dataclass(frozen=True, slots=True)
class ChannelMix:
    rows: tuple[ChannelStat, ...]
    total: int


def channel_mix(rows: Iterable[Interaction]) -> ChannelMix:
    """Volume, reach and mean engagement per channel, ranked by volume."""
    grouped: dict[str, list[Interaction]] = {}
    for row in rows:
        grouped.setdefault(row.channel, []).append(row)

    total = sum(len(group) for group in grouped.values())

    stats = [
        ChannelStat(
            channel=channel,
            interactions=len(group),
            hcps=len({row.hcp_id for row in group if row.hcp_id}),
            avg_engagement=_mean(row.engagement_score for row in group),
            share=100.0 * len(group) / total if total else 0.0,
        )
        for channel, group in grouped.items()
    ]

    # Volume desc; ties fall back to the canonical channel order so the ranking is
    # stable across runs (a dict preserves insertion order, which is row order).
    rank = {channel: index for index, channel in enumerate(schema.CHANNELS)}
    stats.sort(key=lambda stat: (-stat.interactions, rank.get(stat.channel, len(rank))))
    return ChannelMix(rows=tuple(stats), total=total)


# --- 2. monthly trend ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonthStat:
    """One calendar month, split by channel."""

    month: str
    label: str
    counts: dict[str, int]
    total: int


@dataclass(frozen=True, slots=True)
class MonthlyTrend:
    months: tuple[MonthStat, ...]
    channels: tuple[str, ...]
    max_total: int


def monthly_trend(rows: Iterable[Interaction]) -> MonthlyTrend:
    """Interactions per calendar month, broken down by channel."""
    grouped: dict[str, dict[str, int]] = {}
    labels: dict[str, str] = {}
    for row in rows:
        grouped.setdefault(row.month, {})
        grouped[row.month][row.channel] = grouped[row.month].get(row.channel, 0) + 1
        labels.setdefault(row.month, row.month_label)

    channels = _ordered({row.channel for row in rows}, schema.CHANNELS)

    months = tuple(
        MonthStat(
            month=month,
            label=labels[month],
            # Only the channels that actually occurred, re-keyed into channel order
            # so the stacked segments are stable. A month that had no Web activity
            # has no Web key — zero-padding is the chart's job, not the data's.
            counts={
                channel: grouped[month][channel]
                for channel in channels
                if channel in grouped[month]
            },
            total=sum(grouped[month].values()),
        )
        for month in sorted(grouped)
    )

    return MonthlyTrend(
        months=months,
        channels=channels,
        max_total=max((month.total for month in months), default=0),
    )


# --- 3. specialty matrix ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpecialtyRow:
    """One specialty across every channel; `None` where nothing happened."""

    specialty: str
    cells: dict[str, float | None]


@dataclass(frozen=True, slots=True)
class SpecialtyMatrix:
    rows: tuple[SpecialtyRow, ...]
    channels: tuple[str, ...]
    min_value: float
    max_value: float


def specialty_matrix(rows: Iterable[Interaction]) -> SpecialtyMatrix:
    """Mean engagement per specialty × channel, plus the range for the colour scale."""
    grouped: dict[str, dict[str, list[float | None]]] = {}
    for row in rows:
        grouped.setdefault(row.specialty, {}).setdefault(row.channel, []).append(
            row.engagement_score
        )

    channels = _ordered({row.channel for row in rows}, schema.CHANNELS)
    specialties = _ordered(set(grouped), schema.SPECIALTIES)

    matrix = tuple(
        SpecialtyRow(
            specialty=specialty,
            cells={channel: _mean(grouped[specialty].get(channel, ())) for channel in channels},
        )
        for specialty in specialties
    )

    values = [value for row in matrix for value in row.cells.values() if value is not None]
    return SpecialtyMatrix(
        rows=matrix,
        channels=channels,
        min_value=min(values, default=0.0),
        max_value=max(values, default=0.0),
    )


# --- the KPI block ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Kpis:
    """The headline numbers. Rates are percentages, `None` when undefined."""

    interactions: int
    hcps: int
    avg_engagement: float | None
    email_open_rate: float | None
    email_click_rate: float | None


def kpis(rows: Iterable[Interaction]) -> Kpis:
    """Headline counts and rates.

    The click rate is clicks over *opens*, not over emails: an unopened email
    cannot be clicked, so counting it in the denominator would understate the rate.
    """
    materialized = list(rows)

    emails = [row for row in materialized if row.channel in schema.EMAIL_CHANNELS]
    opens = [row for row in emails if row.opened is True]
    clicks = [row for row in opens if row.clicked is True]

    return Kpis(
        interactions=len(materialized),
        hcps=len({row.hcp_id for row in materialized if row.hcp_id}),
        avg_engagement=_mean(row.engagement_score for row in materialized),
        email_open_rate=100.0 * len(opens) / len(emails) if emails else None,
        email_click_rate=100.0 * len(clicks) / len(opens) if opens else None,
    )
