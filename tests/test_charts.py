"""The three charts.

These tests are structural, not pixel-level: they parse the rendered SVG and assert
the properties that would silently break the report — a mark count that no longer
matches the data, a colour that stopped being a design-system slot, or an attribute
form that renders black in one browser.

The palette contract is the load-bearing one. A chart never names a colour; it names
a slot, and `test_no_chart_emits_a_literal_colour` is what keeps that true.
"""

import xml.etree.ElementTree as ET

import pytest

from agenticcoding import charts, metrics, schema, svgcore

# --- helpers ------------------------------------------------------------------


def parse(fragment: str) -> ET.Element:
    """Wrap a chart fragment in a root element so `ElementTree` can read it."""
    return ET.fromstring(f"<svg>{fragment}</svg>")


def marks(root: ET.Element) -> list[ET.Element]:
    """Every element carrying the `mark` class — i.e. one per datum."""
    return [el for el in root.iter() if "mark" in (el.get("class") or "").split()]


def fills(root: ET.Element) -> set[str]:
    """Every fill token a *mark* references, e.g. `ch-1` or `seq-3`.

    Marks only. A value label also paints, but with an ink token that is a property of
    the text rather than of the series, and counting it would turn "which ramp steps
    appear" into "which ramp steps appear plus their inks".
    """
    found = set()
    for el in marks(root):
        style = el.get("style") or ""
        for declaration in style.split(";"):
            if declaration.startswith("fill:var("):
                found.add(declaration.removeprefix("fill:var(--").removesuffix(")"))
    return found


# --- the palette contract -----------------------------------------------------


def test_channel_token_follows_the_entity_not_the_rank():
    """A channel keeps its colour when it moves rank — otherwise a filter repaints."""
    assert charts.channel_token(schema.CHANNELS[0]) == "ch-1"
    assert charts.channel_token(schema.CHANNELS[-1]) == f"ch-{len(schema.CHANNELS)}"


def test_channel_token_is_stable_for_every_canonical_channel():
    tokens = [charts.channel_token(channel) for channel in schema.CHANNELS]

    assert tokens == [f"ch-{index}" for index in range(1, len(schema.CHANNELS) + 1)]
    assert len(set(tokens)) == len(tokens)


def every_chart(sample) -> str:
    """All four charts on one page, so a rule is checked against the whole set."""
    return (
        charts.hero_trend(metrics.monthly_trend(sample))
        + charts.channel_bars(metrics.channel_mix(sample))
        + charts.monthly_columns(metrics.monthly_trend(sample))
        + charts.specialty_heatmap(metrics.specialty_matrix(sample))
    )


def test_no_chart_emits_a_literal_colour(sample):
    """A hex in the output would survive a design swap and look wrong."""
    assert "#" not in every_chart(sample)


def test_colour_is_never_a_presentation_attribute(sample):
    """`fill="var(--ch-1)"` is invalid and renders black in Firefox; `style` is not."""
    rendered = charts.channel_bars(metrics.channel_mix(sample))

    assert 'fill="var(' not in rendered
    assert "style=" in rendered


def test_text_never_wears_a_series_colour(sample):
    """A label's identity comes from the mark beside it, never from its own colour.

    The one fill a text element may carry is an ink: a colour chosen for readability on
    the surface behind it, which says nothing about which series it belongs to.
    """
    painted = [
        el.get("style")
        for el in parse(every_chart(sample)).iter("text")
        if (el.get("style") or "").startswith("fill:var(")
    ]

    assert painted, "the heatmap's values would render black with no ink at all"
    assert all(style.endswith("-ink)") for style in painted), painted


# --- the magnitude ramp -------------------------------------------------------


def test_the_magnitude_ramp_has_seven_steps():
    """Seven, not five: the delivered design's greens were measured against the
    readability floor and the one step with no ink that clears 4.5:1 was dropped, so
    the ramp has to span the same light→dark range in the steps that remain."""
    assert len(charts.SEQUENTIAL) == 7


def test_every_step_of_the_ramp_is_its_own_token():
    """A repeated step is a step that never appears — the bottom of the range would
    silently collapse into the one above it."""
    assert len(set(charts.SEQUENTIAL)) == len(charts.SEQUENTIAL)
    assert [token for token in charts.SEQUENTIAL] == [
        f"seq-{index}" for index in range(1, len(charts.SEQUENTIAL) + 1)
    ]


# --- 0. the hero --------------------------------------------------------------


def test_hero_trend_renders_one_point_per_month(sample):
    """SAMPLE runs März–Mai, so the hero carries three points — the same months the
    trend chart below it stacks by channel."""
    root = parse(charts.hero_trend(metrics.monthly_trend(sample)))

    assert len([el for el in marks(root) if "point" in (el.get("class") or "").split()]) == 3


def test_hero_trend_on_no_months_is_empty_and_parses():
    root = parse(charts.hero_trend(metrics.monthly_trend([])))

    assert marks(root) == []


def test_hero_trend_labels_every_month(sample):
    root = parse(charts.hero_trend(metrics.monthly_trend(sample)))
    labels = [el.text for el in root.iter("text")]

    assert [label for label in labels if label in {"Mär", "Apr", "Mai"}] == [
        "Mär",
        "Apr",
        "Mai",
    ]


def test_hero_trend_carries_the_numbers_in_a_tooltip(sample):
    root = parse(charts.hero_trend(metrics.monthly_trend(sample)))
    tips = [el.get("data-tip") for el in marks(root)]

    assert any(tip and tip.startswith("Mär 2026: 3") for tip in tips)


def test_hero_trend_plots_the_monthly_totals_the_trend_chart_also_carries(sample):
    """The hero is not a separate series — it is the same total, read at a glance.

    A hero fed by anything else could contradict the analysis under it, and the reader
    has no way to tell which of the two is the report.
    """
    trend = metrics.monthly_trend(sample)
    root = parse(charts.hero_trend(trend))
    points = {
        el.get("data-month"): float(el.get("data-value"))
        for el in marks(root)
        if "point" in (el.get("class") or "").split()
    }

    assert points == {month.month: float(month.total) for month in trend.months}


def test_hero_trend_wears_the_magnitude_ramp_not_a_channel_colour(sample):
    """One series of totals has no identity to encode, so it must not borrow a
    channel's slot — the reader would read the hero as that channel."""
    root = parse(charts.hero_trend(metrics.monthly_trend(sample)))

    assert fills(root)
    assert all(token.startswith("seq-") for token in fills(root))


def test_hero_trend_keeps_every_point_inside_the_canvas(sample):
    root = parse(charts.hero_trend(metrics.monthly_trend(sample)))
    xs = [float(el.get("cx")) for el in marks(root)]
    ys = [float(el.get("cy")) for el in marks(root)]

    assert min(xs) >= 0 and max(xs) <= charts.WIDTH
    assert min(ys) >= 0 and max(ys) <= charts.HERO_HEIGHT


def test_hero_trend_on_one_month_still_draws_its_point():
    """A single-month export is a line of one point, which is not a line at all —
    the marker is the chart, and dropping it would render an empty hero."""
    trend = metrics.MonthlyTrend(
        months=(
            metrics.MonthStat(
                month="2026-05", label="Mai", label_full="Mai 2026",
                counts={"F2F Call": 5}, total=5,
            ),
        ),
        channels=("F2F Call",),
        max_total=5,
    )
    root = parse(charts.hero_trend(trend))

    assert len(marks(root)) == 1
    assert "5" in [el.text for el in root.iter("text")]


# --- 1. channel bars ----------------------------------------------------------


def test_channel_bars_renders_one_mark_per_channel(sample):
    root = parse(charts.channel_bars(metrics.channel_mix(sample)))

    assert len(marks(root)) == 3


def test_channel_bars_uses_each_channels_own_colour(sample):
    """Rep Email ranks second by volume but keeps slot 4 — identity, not rank."""
    root = parse(charts.channel_bars(metrics.channel_mix(sample)))

    assert [el.get("data-channel") for el in marks(root)] == ["F2F Call", "Rep Email", "Web"]
    assert fills(root) == {"ch-1", "ch-4", "ch-7"}


def test_channel_bars_names_each_bar(sample):
    root = parse(charts.channel_bars(metrics.channel_mix(sample)))
    labels = [el.text for el in root.iter("text")]

    assert "F2F" in labels
    assert "Web" in labels


def test_channel_bars_carries_the_numbers_in_a_tooltip(sample):
    root = parse(charts.channel_bars(metrics.channel_mix(sample)))
    tips = [el.get("data-tip") for el in marks(root)]

    assert any(tip and tip.startswith("F2F Call: 3") for tip in tips)
    assert any(tip and "70" in tip for tip in tips), "the mean engagement is in the tooltip"


def test_channel_bars_scales_the_longest_bar_to_the_plot_width(sample):
    """Bar length encodes volume, so the largest count must fill the plot."""
    root = parse(charts.channel_bars(metrics.channel_mix(sample)))
    widths = sorted(float(el.get("width")) for el in marks(root))

    assert widths[-1] == pytest.approx(charts.PLOT_WIDTH)
    assert widths[0] == pytest.approx(charts.PLOT_WIDTH * 2 / 3), "Web has 2 of 3"


def test_channel_bars_writes_the_value_at_the_end_of_each_bar(sample):
    root = parse(charts.channel_bars(metrics.channel_mix(sample)))
    labels = [el.text for el in root.iter("text")]

    assert "3 · 37,5 %" in labels, "volume and share, at the data end"
    assert "2 · 25 %" in labels


def test_channel_bars_leaves_a_gap_between_rows(sample):
    """Bars that touch read as one block; the row pitch must exceed the bar."""
    root = parse(charts.channel_bars(metrics.channel_mix(sample)))
    ys = sorted(float(el.get("y")) for el in marks(root))

    assert ys[1] - ys[0] == pytest.approx(charts.BAR_HEIGHT + charts.ROW_GAP)
    assert float(marks(root)[0].get("height")) == pytest.approx(charts.BAR_HEIGHT)


def test_channel_bars_on_empty_input_is_empty_and_parses():
    root = parse(charts.channel_bars(metrics.channel_mix([])))

    assert marks(root) == []


def test_channel_bars_scales_to_the_axis_top_not_to_the_largest_bar():
    """The axis tops out at a round number, so the longest bar must stop short of it.

    Scaling the plot on the largest value instead puts the last gridline past the edge
    of the plot the bar is measured against.
    """
    mix = metrics.ChannelMix(
        rows=(metrics.ChannelStat(channel="F2F Call", interactions=48, hcps=36,
                                  avg_engagement=76.8, avg_duration=30.0, share=100.0),),
        total=48,
    )
    root = parse(charts.channel_bars(mix))
    width = float(marks(root)[0].get("width"))

    assert svgcore.ticks(48.0)[-1] == 50.0, "the axis top rounds up to 50"
    assert width == pytest.approx(charts.PLOT_WIDTH * 48 / 50)


def test_channel_bars_rounds_a_share_the_same_way_the_table_does():
    """17,39 % on the mark and 17,4 % in the table would be the same number twice."""
    mix = metrics.ChannelMix(
        rows=(metrics.ChannelStat(channel="Web", interactions=4, hcps=2,
                                  avg_engagement=None, avg_duration=None, share=17.391),),
        total=23,
    )
    labels = [el.text for el in parse(charts.channel_bars(mix)).iter("text")]

    assert any("17,4 %" in label for label in labels if label)
    assert not any("17,39" in label for label in labels if label)


def test_the_right_margin_fits_a_value_label():
    """The value sits at the end of the bar, outside it — so it needs somewhere to go."""
    margin = charts.WIDTH - (charts.LABEL_GUTTER + charts.PLOT_WIDTH)

    assert margin >= 130, "an 11px monospace label runs to about 80px"


# --- 2. monthly columns -------------------------------------------------------


def test_monthly_columns_renders_one_segment_per_present_channel_month(sample):
    """SAMPLE: Mär has 2 channels, Apr 2, Mai 1 — five segments, not 21."""
    root = parse(charts.monthly_columns(metrics.monthly_trend(sample)))

    assert len(marks(root)) == 5


def test_monthly_columns_labels_every_month(sample):
    root = parse(charts.monthly_columns(metrics.monthly_trend(sample)))
    labels = [el.text for el in root.iter("text")]

    assert [label for label in labels if label in {"Mär", "Apr", "Mai"}] == [
        "Mär",
        "Apr",
        "Mai",
    ]


def test_trend_legend_names_every_channel_and_swatches_it(sample):
    """Three or more series means a legend, always — identity is never colour alone.

    The legend is HTML, not SVG: the delivered design lays it out as a wrapping list
    above the chart, which is a thing a browser does well and a `<text>` run does not.
    """
    legend = charts.trend_legend(metrics.monthly_trend(sample))

    assert '<ul class="legend">' in legend
    for channel in ("F2F", "Rep Email", "Web"):
        assert f"</i>{channel}</li>" in legend, channel


def test_trend_legend_swatches_carry_a_slot_not_a_colour(sample):
    """The swatch is the channel's own identity, and it must survive a design swap."""
    legend = charts.trend_legend(metrics.monthly_trend(sample))

    assert "background:var(--ch-1)" in legend
    assert "background:var(--ch-7)" in legend
    assert "#" not in legend


def test_trend_legend_on_no_months_is_empty():
    assert charts.trend_legend(metrics.monthly_trend([])) == ""


def test_numeric_axis_labels_wear_the_tick_class(sample):
    """The design sets numbers in muted ink at 11px and names in secondary at 12px."""
    rendered = charts.channel_bars(metrics.channel_mix(sample))

    assert 'class="tick"' in rendered
    assert 'class="axis-label"' not in rendered


def test_category_labels_wear_the_label_class(sample):
    rendered = charts.channel_bars(metrics.channel_mix(sample)) + charts.specialty_heatmap(
        metrics.specialty_matrix(sample)
    )

    assert 'class="label"' in rendered
    assert "F2F" in rendered


def test_monthly_columns_leaves_a_surface_gap_between_stacked_segments(sample):
    """Segments that touch read as one block; a 2px gap keeps them separable."""
    root = parse(charts.monthly_columns(metrics.monthly_trend(sample)))

    march = [el for el in marks(root) if el.get("data-month") == "2026-03"]
    assert len(march) == 2

    boxes = sorted((float(el.get("y")), float(el.get("height"))) for el in march)
    (upper_y, upper_h), (lower_y, _) = boxes

    assert upper_y + upper_h == pytest.approx(lower_y - 2.0), "the 2px surface gap"


def test_monthly_columns_stacks_from_the_baseline_upwards(sample):
    """The first channel in report order sits on the axis; the last sits on top."""
    root = parse(charts.monthly_columns(metrics.monthly_trend(sample)))

    march = {el.get("data-channel"): float(el.get("y")) for el in marks(root)
             if el.get("data-month") == "2026-03"}

    assert march["F2F Call"] > march["Rep Email"], "F2F is the lower segment"


def test_monthly_columns_carries_the_numbers_in_a_tooltip(sample):
    root = parse(charts.monthly_columns(metrics.monthly_trend(sample)))
    tips = [el.get("data-tip") for el in marks(root)]

    assert any(tip and "Mär" in tip and "F2F Call" in tip for tip in tips)


def test_monthly_columns_on_empty_input_is_empty_and_parses():
    root = parse(charts.monthly_columns(metrics.monthly_trend([])))

    assert marks(root) == []


def test_monthly_columns_keeps_every_tick_inside_the_plot():
    """A 45-high column scales to an axis that tops out at 50 — and 50 must be on the plot.

    Scaling on the tallest column instead pushes the top gridline off the top of the
    viewBox, where its label renders clipped or invisible.
    """
    trend = metrics.MonthlyTrend(
        months=(
            metrics.MonthStat(
                month="2026-05", label="Mai", label_full="Mai 2026",
                counts={"F2F Call": 45}, total=45,
            ),
        ),
        channels=("F2F Call",),
        max_total=45,
    )
    root = parse(charts.monthly_columns(trend))
    gridlines = [float(el.get("y1")) for el in root.iter("line") if el.get("class") == "grid"]

    assert svgcore.ticks(45.0)[-1] == 50.0, "the axis top rounds up to 50"
    assert min(gridlines) == pytest.approx(charts.PLOT_TOP), "the top tick sits on the plot top"
    assert max(gridlines) == pytest.approx(charts.PLOT_TOP + charts.PLOT_HEIGHT)


# --- 3. specialty heatmap -----------------------------------------------------


def test_heatmap_renders_a_cell_per_present_specialty_channel_pair(sample):
    """SAMPLE: Oncology has 3 channels, Cardiology 2 — the sixth pair is absent."""
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(sample)))

    assert len(marks(root)) == 5


def test_heatmap_marks_an_absent_combination_rather_than_leaving_it_blank(sample):
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(sample)))
    empty = [el for el in root.iter() if "cell-empty" in (el.get("class") or "").split()]

    assert len(empty) == 1


def test_heatmap_uses_the_sequential_ramp_not_the_channel_colours(sample):
    """Magnitude takes one hue light→dark; the categorical slots are for identity."""
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(sample)))

    assert fills(root)
    assert all(token.startswith("seq-") for token in fills(root))


def test_heatmap_writes_the_value_into_every_present_cell(sample):
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(sample)))
    labels = [el.text for el in root.iter("text")]

    assert "70" in labels, "Oncology × F2F"
    assert "25" in labels, "Cardiology × Rep Email"


def test_heatmap_labels_the_rows_and_columns(sample):
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(sample)))
    labels = [el.text for el in root.iter("text")]

    assert "Onkologie" in labels
    assert "Kardiologie" in labels
    assert "F2F" in labels


def test_heatmap_rows_are_labelled_in_german_not_by_their_key(sample):
    """`Cardiology` is what the cleaner matches on; a reader is shown `Kardiologie`."""
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(sample)))
    labels = [el.text for el in root.iter("text")]

    assert "Oncology" not in labels
    assert "General Medicine" not in labels


def test_heatmap_cells_are_rounded_like_the_design(sample):
    """The delivered design rounds every cell. `rx` is geometry, so it is not a
    design token — but a cell that lost it would read as a different chart."""
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(sample)))

    assert all(el.get("rx") == "4" for el in marks(root))


def test_the_heatmap_gutter_fits_its_longest_label():
    """A right-anchored label grows *leftward*, and the longest German specialty name
    is `Allgemeinmedizin`. Too narrow a gutter pushes it past the left of the canvas,
    where the viewBox clips it and the row loses its name entirely.

    The real measurement is taken by looking at the rendered page; this is the
    regression floor that stops someone narrowing the gutter back to the 110 that fit
    `General Medicine`, on the estimate of a 12px glyph advancing about 7px.
    """
    longest = max(len(schema.specialty_label(name)) for name in schema.SPECIALTIES)
    label_start = charts.HEATMAP_GUTTER - charts.HEATMAP_LABEL_GAP - longest * 7

    assert longest == len("Allgemeinmedizin")
    assert label_start >= 0, f"the longest label would start at x={label_start}"


def test_heatmap_puts_the_two_extremes_at_the_ends_of_the_ramp(sample):
    """The colour scale must span the data, or every cell looks mid-range."""
    matrix = metrics.specialty_matrix(sample)
    root = parse(charts.specialty_heatmap(matrix))

    tokens = sorted(fills(root))
    assert tokens[0] == charts.SEQUENTIAL[0]
    assert tokens[-1] == charts.SEQUENTIAL[-1]


def test_heatmap_on_empty_input_is_empty_and_parses():
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix([])))

    assert marks(root) == []


def test_heatmap_on_a_single_valued_matrix_does_not_divide_by_zero():
    """Every cell equal means the range is zero wide — all cells land on one step."""
    from conftest import interaction

    rows = [interaction(engagement_score=50.0), interaction(interaction_id="I2", engagement_score=50.0)]
    root = parse(charts.specialty_heatmap(metrics.specialty_matrix(rows)))

    assert len(fills(root)) == 1
