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


def test_no_chart_emits_a_literal_colour(sample):
    """A hex in the output would survive a design swap and look wrong."""
    rendered = (
        charts.channel_bars(metrics.channel_mix(sample))
        + charts.monthly_columns(metrics.monthly_trend(sample))
        + charts.specialty_heatmap(metrics.specialty_matrix(sample))
    )

    assert "#" not in rendered


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
    rendered = (
        charts.channel_bars(metrics.channel_mix(sample))
        + charts.monthly_columns(metrics.monthly_trend(sample))
        + charts.specialty_heatmap(metrics.specialty_matrix(sample))
    )
    painted = [
        el.get("style")
        for el in parse(rendered).iter("text")
        if (el.get("style") or "").startswith("fill:var(")
    ]

    assert painted, "the heatmap's values would render black with no ink at all"
    assert all(style.endswith("-ink)") for style in painted), painted


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

    assert "3 · 37.5 %" in labels, "volume and share, at the data end"
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
                                  avg_engagement=76.8, share=100.0),),
        total=48,
    )
    root = parse(charts.channel_bars(mix))
    width = float(marks(root)[0].get("width"))

    assert svgcore.ticks(48.0)[-1] == 50.0, "the axis top rounds up to 50"
    assert width == pytest.approx(charts.PLOT_WIDTH * 48 / 50)


def test_channel_bars_rounds_a_share_the_same_way_the_table_does():
    """17.39 % on the mark and 17.4 % in the table would be the same number twice."""
    mix = metrics.ChannelMix(
        rows=(metrics.ChannelStat(channel="Web", interactions=4, hcps=2,
                                  avg_engagement=None, share=17.391),),
        total=23,
    )
    labels = [el.text for el in parse(charts.channel_bars(mix)).iter("text")]

    assert any("17.4 %" in label for label in labels if label)
    assert not any("17.39" in label for label in labels if label)


def test_the_right_margin_fits_a_value_label():
    """The value sits at the end of the bar, outside it — so it needs somewhere to go."""
    margin = charts.WIDTH - (charts.LABEL_GUTTER + charts.PLOT_WIDTH)

    assert margin >= 130, "an 11px monospace label runs to about 80px"


# --- 2. monthly columns -------------------------------------------------------


def test_monthly_columns_renders_one_segment_per_present_channel_month(sample):
    """SAMPLE: Mar has 2 channels, Apr 2, May 1 — five segments, not 21."""
    root = parse(charts.monthly_columns(metrics.monthly_trend(sample)))

    assert len(marks(root)) == 5


def test_monthly_columns_labels_every_month(sample):
    root = parse(charts.monthly_columns(metrics.monthly_trend(sample)))
    labels = [el.text for el in root.iter("text")]

    assert [label for label in labels if label in {"Mar", "Apr", "May"}] == [
        "Mar",
        "Apr",
        "May",
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

    assert any(tip and "Mar" in tip and "F2F Call" in tip for tip in tips)


def test_monthly_columns_on_empty_input_is_empty_and_parses():
    root = parse(charts.monthly_columns(metrics.monthly_trend([])))

    assert marks(root) == []


def test_monthly_columns_keeps_every_tick_inside_the_plot():
    """A 45-high column scales to an axis that tops out at 50 — and 50 must be on the plot.

    Scaling on the tallest column instead pushes the top gridline off the top of the
    viewBox, where its label renders clipped or invisible.
    """
    trend = metrics.MonthlyTrend(
        months=(metrics.MonthStat(month="2026-05", label="May", counts={"F2F Call": 45}, total=45),),
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

    assert "Oncology" in labels
    assert "Cardiology" in labels
    assert "F2F" in labels


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
