"""The three charts, composed from the primitives in `svgcore`.

Each function takes a metrics dataclass and returns a complete `<svg>` element as a
string. Nothing here knows a colour, a font or a size that matters to the design:
marks carry `style="fill:var(--ch-3)"` and text carries a class. The template decides
what those look like, which is what makes a design swap a template edit.

Three rules the tests enforce:

* **Colour follows the entity, not the rank.** `channel_token` maps a channel to its
  slot by position in `schema.CHANNELS`, so a channel keeps its colour when it moves
  up or down the ranking.
* **Text never wears a series colour.** Data marks carry the identity; a label's own
  fill may only ever be an `-ink` token — a colour chosen for readability on the surface
  behind it. That is also what keeps `fills()` in the tests meaning "series colours".
* **Every mark is reachable.** Each one carries a `data-tip`, and every chart has a
  table twin in the report, so no value exists only inside a hover.
"""

from __future__ import annotations

from . import metrics, schema, svgcore

# --- shared geometry ----------------------------------------------------------

WIDTH = 720
# The plot stops at 576 and the remaining 144px is the value-label margin: a bar's
# value is written just outside its data end, so the widest label the data can produce
# ("48 · 26.1 %", about 80px at 11px monospace) has to fit between there and the edge.
# At 640 the label was clipped by the viewBox instead.
PLOT_WIDTH = 480
LABEL_GUTTER = 96

PLOT_TOP = 8
PLOT_HEIGHT = 200

BAR_HEIGHT = 22
ROW_GAP = 14

AXIS_BAND = 28

# The surface gap between two stacked segments and between adjacent bars. Without it
# two touching fills read as one block and the stack's parts become uncountable.
GAP = 2.0

# Magnitude ramp for the heatmap: one hue, light to dark. The categorical channel
# slots are for identity and must not be reused here.
SEQUENTIAL: tuple[str, ...] = ("seq-1", "seq-2", "seq-3", "seq-4", "seq-5")


def channel_token(channel: str) -> str:
    """The design-system slot for a channel — by identity, never by rank.

    The cleaner drops rows with an unrecognized channel, so a `ValueError` here would
    mean a bug upstream, not bad data.
    """
    return f"ch-{schema.CHANNELS.index(channel) + 1}"


def _svg(content: str, height: float) -> str:
    """Wrap a fragment in its root element. The template styles `.chart`."""
    return (
        f'<svg class="chart" viewBox="0 0 {svgcore.fmt(WIDTH)} {svgcore.fmt(height)}" '
        f'role="img" preserveAspectRatio="xMidYMid meet">{content}</svg>'
    )


def _short(channel: str) -> str:
    """The axis-sized name for a channel; falls back to the full name."""
    return schema.CHANNEL_SHORT.get(channel, channel)


def _gridline(x1: float, y1: float, x2: float, y2: float) -> str:
    """A hairline rule. Solid, never dashed — dashes read as 'projected' or 'missing'.

    The stroke comes from the template's `.chart .grid` rule rather than from here:
    a rule's colour is part of the theme, and the theme is the designer's file.
    """
    return svgcore.element("line", cls="grid", x1=x1, y1=y1, x2=x2, y2=y2)


def trend_legend(trend: metrics.MonthlyTrend) -> str:
    """The channel legend, as HTML — a wrapping list above the chart.

    HTML rather than an SVG `<text>` run because a legend is a list of things that
    must reflow on a phone, and reflow is what a browser already does. The swatch is
    the channel's own slot, so a colour swap is still a template edit.
    """
    if not trend.channels:
        return ""
    items = "".join(
        f'<li><i style="background:var(--{channel_token(channel)})"></i>'
        f"{svgcore.esc(_short(channel))}</li>"
        for channel in trend.channels
    )
    return f'<ul class="legend">{items}</ul>'


# --- 1. channel mix: ranked horizontal bars -----------------------------------


def channel_bars(mix: metrics.ChannelMix) -> str:
    """Volume per channel as ranked horizontal bars.

    Length encodes the volume, so every bar is the same thickness and one channel's
    colour is its own identity — there is no value ramp on top of the length.
    """
    if not mix.rows:
        return ""

    tallest = max(row.interactions for row in mix.rows)
    # The scale runs to the axis top, not to the largest bar. Scaling on the bar puts
    # the last gridline beyond the edge of the plot the bars are measured against.
    ticks = svgcore.ticks(float(tallest))
    x_scale = svgcore.linear((0.0, ticks[-1]), (0.0, float(PLOT_WIDTH)))
    plot_bottom = PLOT_TOP + len(mix.rows) * (BAR_HEIGHT + ROW_GAP) - ROW_GAP

    parts: list[str] = []

    # Grid first, so the bars sit on top of it rather than behind it.
    for tick in ticks:
        x = LABEL_GUTTER + x_scale(tick)
        parts.append(_gridline(x, PLOT_TOP, x, plot_bottom))
        parts.append(
            svgcore.element(
                "text", svgcore.fmt(tick), cls="tick",
                x=x, y=plot_bottom + 17, **{"text-anchor": "middle"},
            )
        )

    for index, row in enumerate(mix.rows):
        y = PLOT_TOP + index * (BAR_HEIGHT + ROW_GAP)
        width = x_scale(row.interactions)
        # `share` rather than `fmt`: the table twin rounds a share to one decimal, and
        # the same number must not appear two ways on one page.
        tip = (
            f"{row.channel}: {row.interactions} interactions "
            f"({svgcore.share(row.share)}), {row.hcps} HCPs, "
            f"avg engagement {svgcore.fmt(row.avg_engagement)}"
        )
        parts.append(
            svgcore.element(
                "rect", cls="mark", x=LABEL_GUTTER, y=y, width=width, height=BAR_HEIGHT,
                rx=4,
                # Square the baseline end: a bar must be anchored, not float.
                clip_path="inset(0 0 0 0 round 0 4px 4px 0)",
                style=svgcore.paint(channel_token(row.channel)),
                **{"data-tip": tip, "data-channel": row.channel},
            )
        )
        parts.append(
            svgcore.element(
                "text", _short(row.channel), cls="label",
                x=LABEL_GUTTER - 10, y=y + BAR_HEIGHT / 2 + 4,
                **{"text-anchor": "end"},
            )
        )
        parts.append(
            svgcore.element(
                "text", f"{row.interactions} · {svgcore.share(row.share)}",
                cls="value", x=LABEL_GUTTER + width + 8, y=y + BAR_HEIGHT / 2 + 4,
            )
        )

    return _svg("".join(parts), plot_bottom + AXIS_BAND)


# --- 2. monthly trend: stacked columns by channel -----------------------------


def monthly_columns(trend: metrics.MonthlyTrend) -> str:
    """Interactions per month, stacked by channel.

    The stack is scaled so that the tallest month *including its surface gaps* fills
    the plot exactly. Scaling on the raw total instead would push the top segment past
    the axis by `(segments - 1) × gap`.

    The scale runs to the axis top rather than to `max_total`, so every gridline the
    axis draws lands inside the plot. Scaling on the data puts the top tick above the
    viewBox, where it renders clipped.
    """
    if not trend.months:
        return ""

    plot_bottom = PLOT_TOP + PLOT_HEIGHT
    widest = max(sum(1 for count in month.counts.values() if count > 0) for month in trend.months)
    usable = PLOT_HEIGHT - max(0, widest - 1) * GAP
    ticks = svgcore.ticks(float(trend.max_total))
    y_scale = svgcore.linear((0.0, ticks[-1]), (0.0, float(usable)))

    band = PLOT_WIDTH / len(trend.months)
    bar_width = min(24.0, band * 0.7)

    parts: list[str] = []

    for tick in ticks:
        y = plot_bottom - y_scale(tick)
        parts.append(_gridline(LABEL_GUTTER, y, LABEL_GUTTER + PLOT_WIDTH, y))
        parts.append(
            svgcore.element(
                "text", svgcore.fmt(tick), cls="tick",
                x=LABEL_GUTTER - 10, y=y + 4, **{"text-anchor": "end"},
            )
        )

    for index, month in enumerate(trend.months):
        centre = LABEL_GUTTER + (index + 0.5) * band
        left = centre - bar_width / 2
        present = [channel for channel in trend.channels if month.counts.get(channel, 0) > 0]
        topmost = present[-1] if present else None

        cursor = float(plot_bottom)
        for channel in present:
            count = month.counts[channel]
            height = y_scale(count)
            top = cursor - height
            parts.append(
                svgcore.element(
                    "rect", cls="mark", x=left, y=top, width=bar_width, height=height,
                    rx=4 if channel == topmost else None,
                    # Only the top of the stack is a data end; the rest are joins.
                    clip_path=(
                        "inset(0 0 0 0 round 4px 4px 0 0)" if channel == topmost else None
                    ),
                    style=svgcore.paint(channel_token(channel)),
                    **{
                        "data-tip": f"{month.label} · {channel}: {count}",
                        "data-month": month.month,
                        "data-channel": channel,
                    },
                )
            )
            cursor = top - GAP

        parts.append(
            svgcore.element(
                "text", month.label, cls="label",
                x=centre, y=plot_bottom + 17, **{"text-anchor": "middle"},
            )
        )

    return _svg("".join(parts), plot_bottom + AXIS_BAND)


# --- 3. specialty matrix: heatmap ---------------------------------------------


def specialty_heatmap(matrix: metrics.SpecialtyMatrix) -> str:
    """Mean engagement per specialty × channel, on a single-hue magnitude ramp.

    An absent combination is drawn as a marked empty cell rather than left blank: a
    blank is indistinguishable from a rendering bug, and from a zero.
    """
    if not matrix.rows or not matrix.channels:
        return ""

    gutter = 110.0
    cell_width = (WIDTH - gutter) / len(matrix.channels)
    cell_height = 34.0
    plot_bottom = PLOT_TOP + len(matrix.rows) * cell_height

    span = matrix.max_value - matrix.min_value
    steps = len(SEQUENTIAL) - 1

    parts: list[str] = []

    for row_index, row in enumerate(matrix.rows):
        y = PLOT_TOP + row_index * cell_height
        parts.append(
            svgcore.element(
                "text", row.specialty, cls="label",
                x=gutter - 12, y=y + cell_height / 2 + 4, **{"text-anchor": "end"},
            )
        )
        for column_index, channel in enumerate(matrix.channels):
            x = gutter + column_index * cell_width
            value = row.cells.get(channel)

            if value is None:
                parts.append(
                    svgcore.element(
                        "rect", cls="cell cell-empty",
                        x=x + 1, y=y + 1, width=cell_width - 2, height=cell_height - 2,
                        **{"data-tip": f"{row.specialty} × {channel}: no interactions"},
                    )
                )
                continue

            # A zero-width range (every cell equal) lands mid-ramp rather than
            # dividing by zero.
            depth = round(((value - matrix.min_value) / span) * steps) if span else steps // 2
            parts.append(
                svgcore.element(
                    "rect", cls="mark cell", x=x + 1, y=y + 1,
                    width=cell_width - 2, height=cell_height - 2,
                    style=svgcore.paint(SEQUENTIAL[depth]),
                    **{
                        "data-tip": f"{row.specialty} × {channel}: {svgcore.fmt(value)}",
                        "data-specialty": row.specialty,
                        "data-channel": channel,
                    },
                )
            )
            # The ink is a colour decision and lives with the other colours, one token
            # per ramp step. Choosing it here by depth would be a second definition of
            # the theme: the ramp runs light→dark on a light surface and dark→light on
            # a dark one, so the same depth is a dark cell in one mode and a pale one in
            # the other. The template owns which ink each step needs.
            parts.append(
                svgcore.element(
                    "text", svgcore.fmt(value), cls="cell-value",
                    style=svgcore.paint(f"{SEQUENTIAL[depth]}-ink"),
                    x=x + cell_width / 2, y=y + cell_height / 2 + 4,
                    **{"text-anchor": "middle"},
                )
            )

    for column_index, channel in enumerate(matrix.channels):
        parts.append(
            svgcore.element(
                "text", _short(channel), cls="label",
                x=gutter + (column_index + 0.5) * cell_width,
                y=plot_bottom + 17, **{"text-anchor": "middle"},
            )
        )

    return _svg("".join(parts), plot_bottom + AXIS_BAND)
