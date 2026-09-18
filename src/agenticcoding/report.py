"""The view model: metrics and charts in, template slots out.

This is the only module that knows both what the numbers mean and what the template
calls them. Everything it emits is a **string, already formatted** — the template has
no way to format a number, so `svgcore.fmt` decides here and the design never has to.

It renders three things of its own, and nothing more:

* the **takeaways**, which are sentences about this dataset and so cannot live in a
  template that is shared across datasets;
* the **table twins**, because every value a chart encodes must also exist as text —
  a table is also what carries the report for a reader who cannot use the hover;
* the **page shell**, which is boilerplate rather than design.

Every static word — headings, labels, section titles, units — belongs to the template.
That split is what makes the design handoff a template edit.
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from collections.abc import Iterable, Sequence
from importlib import resources
from pathlib import Path

from . import charts, clean, metrics, schema, svgcore
from .render import render

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# The fragment's leading `<title>` and `<style>` are hoisted into `<head>` so the
# written file is a valid document. The published page gets the same treatment from
# the artifact host, which is why the template itself stays a fragment.
_LEADING = re.compile(
    r"\s*(?:<!--.*?-->|<title\b[^>]*>.*?</title>|<style\b[^>]*>.*?</style>)",
    re.DOTALL | re.IGNORECASE,
)

_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
{head}</head>
<body>
{body}</body>
</html>
"""


# --- the template -------------------------------------------------------------


def _packaged_template(name: str) -> str | None:
    """The template as installed package data, if the build shipped it."""
    try:
        return (resources.files(__package__) / "templates" / name).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError, TypeError, OSError):
        return None


def load_template(name: str = "report.html") -> str:
    """A template from the installed package, or from the source tree.

    `uv_build` package data is not something to rely on, so a checkout falls back to
    reading the file beside this module. Both paths are the same file in a source
    checkout, which is exactly the point: rendering must work either way.

    `name` selects among the files in `templates/`. The default is the design the
    tool renders; naming another one — `design-template.html`, or a file you add
    beside it — is how a new design is tried without touching the live one.
    """
    packaged = _packaged_template(name)
    if packaged is not None:
        return packaged
    return (Path(__file__).resolve().parent / "templates" / name).read_text("utf-8")


def document(slots: dict[str, str], template: str) -> str:
    """Render the template and wrap it in a standalone page.

    The template is a fragment — no `<html>`, `<head>` or `<body>` — because that is
    the form the artifact host expects and the form a designer hands over. The shell
    this adds is boilerplate, not design, so it lives here rather than in the file a
    designer edits.
    """
    fragment = render(template, slots)
    head, rest = _split_head(fragment)
    return _SHELL.format(head=head, body=rest)


def _split_head(fragment: str) -> tuple[str, str]:
    """Peel the leading `<title>`/`<style>`/comment blocks off a rendered fragment."""
    head: list[str] = []
    rest = fragment
    while match := _LEADING.match(rest):
        head.append(match.group(0).strip())
        rest = rest[match.end() :]
    return "".join(head), rest


# --- small formatting helpers -------------------------------------------------


def _count(value: int) -> str:
    return str(value)


def _share(value: float | None, decimals: int = 1) -> str:
    return svgcore.share(value, decimals)


def _period(rows: Sequence[schema.Interaction]) -> str:
    """The span the data covers, as prose. Never guessed — read off the rows."""
    if not rows:
        return "No period"
    first, last = min(row.date for row in rows), max(row.date for row in rows)
    if (first.year, first.month) == (last.year, last.month):
        return f"{_MONTHS[first.month - 1]} {first.year}"
    if first.year == last.year:
        return f"{_MONTHS[first.month - 1]} – {_MONTHS[last.month - 1]} {first.year}"
    return (
        f"{_MONTHS[first.month - 1]} {first.year} – "
        f"{_MONTHS[last.month - 1]} {last.year}"
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """A table twin. Escaped like everything else — a specialty label is input.

    The first cell of a row is a `th`: it names the row, which is what makes the
    table readable by a screen reader rather than a grid of anonymous numbers.
    """
    head = "".join(f'<th scope="col">{svgcore.esc(header)}</th>' for header in headers)
    body = []
    for row in rows:
        cells = []
        for index, value in enumerate(row):
            if index == 0:
                cells.append(f'<th scope="row">{svgcore.esc(value)}</th>')
            else:
                cells.append(f'<td class="num">{svgcore.esc(value)}</td>')
        body.append(f"<tr>{''.join(cells)}</tr>")
    return (
        f"<table><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _row_means(matrix: metrics.SpecialtyMatrix) -> list[tuple[float, str]]:
    """Each specialty's mean over its present cells, best first."""
    scored = []
    for row in matrix.rows:
        values = [value for value in row.cells.values() if value is not None]
        if values:
            scored.append((statistics.fmean(values), row.specialty))
    return sorted(scored, key=lambda pair: -pair[0])


# --- the takeaways ------------------------------------------------------------


def _bold(text: str) -> str:
    """The emphasis an insight sentence carries, with its subject escaped first.

    A takeaway goes into the page through a *raw* slot — it carries its own markup —
    so every label inside it is escaped here, at the one place that knows which parts
    of the sentence came out of the CSV.
    """
    return f"<b>{svgcore.esc(text)}</b>"


def _channel_takeaway(mix: metrics.ChannelMix) -> str:
    if not mix.rows:
        return "No interactions were recorded in this period."
    leader = mix.rows[0]
    best = max(
        (row for row in mix.rows if row.avg_engagement is not None),
        key=lambda row: row.avg_engagement,
        default=None,
    )
    sentence = (
        f"{_bold(leader.channel)} carries the most activity — {leader.interactions} "
        f"interactions, {_share(leader.share)} of the total"
    )
    if best is not None:
        # Name the channel whenever it is not the one already named. "— and posts the
        # highest average engagement" reads as a fact about `leader`, so an unnamed
        # `best` would credit the volume leader with another channel's score.
        subject = "— and posts" if best is leader else f"— and {_bold(best.channel)} posts"
        sentence += f" {subject} the highest average engagement, at {svgcore.fmt(best.avg_engagement)}"
    return sentence + "."


def _trend_takeaway(trend: metrics.MonthlyTrend) -> str:
    if not trend.months:
        return "No interactions were recorded in this period."
    peak = max(trend.months, key=lambda month: month.total)
    last = trend.months[-1]
    if len(trend.months) == 1:
        return f"All {last.total} interactions fall in {_bold(last.label)}."
    return (
        f"Volume peaked in {_bold(peak.label)} at {peak.total} interactions and closed "
        f"at {last.total} in {last.label}."
    )


def _specialty_takeaway(matrix: metrics.SpecialtyMatrix) -> str:
    ranked = _row_means(matrix)
    if not ranked:
        return "No specialty had a scored interaction in this period."
    if len(ranked) == 1:
        return f"{_bold(ranked[0][1])} is the only specialty with scored interactions."
    (top_value, top_name), (bottom_value, bottom_name) = ranked[0], ranked[-1]
    return (
        f"{_bold(top_name)} shows the strongest mean engagement at "
        f"{svgcore.fmt(top_value)}, ahead of {bottom_name} at {svgcore.fmt(bottom_value)}."
    )


def _hero_tagline(kpis: metrics.Kpis, period: str) -> str:
    """The sentence the page opens with, carrying its own two headline counts."""
    return (
        f"{kpis.interactions} interactions with {kpis.hcps} health care professionals "
        f"from {period} — cleaned, analysed, and accounted for."
    )


def _hcps_note(kpis: metrics.Kpis) -> str:
    """Interactions per HCP: the reach figure made comparable across periods."""
    if not kpis.hcps:
        return "no HCP recorded"
    return f"{svgcore.fmt(kpis.interactions / kpis.hcps, 1)} interactions per HCP"


def _click_note(kpis: metrics.Kpis) -> str:
    """Clicks over opens — an unopened email cannot be clicked, so it is not counted."""
    if kpis.email_click_rate is None:
        return "no opens recorded"
    return f"{svgcore.share(kpis.email_click_rate, 0)} of opens clicked"


# --- the slot dictionary ------------------------------------------------------


def build_slots(
    rows: Iterable[schema.Interaction],
    quality: clean.QualityReport,
    *,
    source_file: str,
    generated_at: str,
    period_label: str | None = None,
) -> dict[str, str]:
    """Everything the template asks for, formatted and ready to substitute."""
    data = list(rows)
    period = period_label or _period(data)

    mix = metrics.channel_mix(data)
    trend = metrics.monthly_trend(data)
    matrix = metrics.specialty_matrix(data)
    kpis = metrics.kpis(data)

    missing_scores = sum(1 for row in data if row.engagement_score is None)

    return {
        # header
        "PERIOD_LABEL": period,
        "GENERATED_AT": generated_at,
        "SOURCE_FILE": source_file,
        "HERO_TAGLINE": _hero_tagline(kpis, period),
        # the KPI strip
        "KPI_INTERACTIONS": _count(kpis.interactions),
        "KPI_INTERACTIONS_NOTE": f"from {_count(quality.rows_in)} raw rows",
        "KPI_HCPS": _count(kpis.hcps),
        "KPI_HCPS_NOTE": _hcps_note(kpis),
        "KPI_AVG_ENGAGEMENT": svgcore.fmt(kpis.avg_engagement),
        "KPI_EMAIL_OPEN_RATE": _share(kpis.email_open_rate),
        "KPI_EMAIL_OPEN_RATE_NOTE": _click_note(kpis),
        # data quality
        "QUALITY_HEADLINE": (
            f"{quality.rows_in} raw rows → {quality.rows_out} analysable "
            f"({svgcore.fmt(quality.analyzable_share, 0)} %)"
        ),
        "QUALITY_TABLE": _table(
            ("Stage", "Rows"),
            [(note.label, _count(note.count)) for note in quality.notes],
        ),
        "MISSING_SCORE_NOTE": (
            f"Engagement score is missing on {missing_scores} of {len(data)} interactions. "
            f"Those rows count toward volume and are excluded from every average — "
            f"nothing is imputed."
        ),
        # 1 · channel mix
        "CHANNEL_TAKEAWAY": _channel_takeaway(mix),
        "CHANNEL_CHART": charts.channel_bars(mix),
        "CHANNEL_TABLE": _table(
            ("Channel", "Interactions", "Share", "HCPs", "Avg engagement"),
            [
                (
                    row.channel,
                    _count(row.interactions),
                    _share(row.share),
                    _count(row.hcps),
                    svgcore.fmt(row.avg_engagement),
                )
                for row in mix.rows
            ],
        ),
        # 2 · monthly trend
        "TREND_TAKEAWAY": _trend_takeaway(trend),
        "TREND_LEGEND": charts.trend_legend(trend),
        "TREND_CHART": charts.monthly_columns(trend),
        "TREND_TABLE": _table(
            ("Month", "Total", *trend.channels),
            [
                (
                    month.label,
                    _count(month.total),
                    *[_count(month.counts.get(channel, 0)) for channel in trend.channels],
                )
                for month in trend.months
            ],
        ),
        # 3 · specialty matrix
        "SPECIALTY_TAKEAWAY": _specialty_takeaway(matrix),
        "SPECIALTY_CHART": charts.specialty_heatmap(matrix),
        "SPECIALTY_TABLE": _table(
            ("Specialty", *matrix.channels),
            [
                (
                    row.specialty,
                    *[
                        svgcore.fmt(row.cells.get(channel))
                        for channel in matrix.channels
                    ],
                )
                for row in matrix.rows
            ],
        ),
    }
