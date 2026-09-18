"""The geometry layer under the charts.

`charts.py` composes; this module owns the primitives every chart needs — escaping,
scales, tick rounding, number formatting, and the one rule that keeps the palette
swappable: colour is *always* a CSS custom property, never a literal hex.

Two of these functions carry more weight than their size suggests:

* `esc` is the only thing standing between a CSV cell and the rendered page. Channel
  and specialty labels come from an untrusted export, so they are escaped on the way
  into both text content and attribute values.
* `paint` is why a design swap is a template edit. A chart never names a colour; it
  names a slot, and the template decides what that slot looks like.
"""

import pytest

from agenticcoding import svgcore

# --- escaping -----------------------------------------------------------------


def test_escape_neutralizes_markup_characters():
    assert svgcore.esc("A & B") == "A &amp; B"
    assert svgcore.esc("F2F < Call") == "F2F &lt; Call"
    assert svgcore.esc("a > b") == "a &gt; b"


def test_escape_neutralizes_quotes():
    assert svgcore.esc('say "hi"') == "say &quot;hi&quot;"
    assert svgcore.esc("it's") == "it&apos;s"


def test_escape_leaves_ordinary_labels_alone():
    assert svgcore.esc("Screen-to-Screen Call") == "Screen-to-Screen Call"
    assert svgcore.esc("Oncology") == "Oncology"


def test_escape_defuses_a_script_payload():
    hostile = '<script>alert("x")</script>'

    escaped = svgcore.esc(hostile)

    assert "<script>" not in escaped
    assert '"' not in escaped


def test_escape_accepts_non_string_values():
    assert svgcore.esc(42) == "42"
    assert svgcore.esc(None) == ""


# --- the element builder ------------------------------------------------------


def test_element_renders_attributes_and_text():
    assert svgcore.element("text", "F2F", x=10, y=20) == '<text x="10" y="20">F2F</text>'


def test_element_self_closes_when_it_has_no_text():
    assert svgcore.element("rect", x=0, y=0, width=10, height=5) == (
        '<rect x="0" y="0" width="10" height="5"/>'
    )


def test_element_escapes_text_content():
    assert svgcore.element("text", "A & B", x=1) == '<text x="1">A &amp; B</text>'


def test_element_escapes_attribute_values():
    rendered = svgcore.element("text", "label", **{"data-tip": '"><script>'})

    assert "<script>" not in rendered
    assert "&quot;&gt;&lt;script&gt;" in rendered


def test_element_omits_none_attributes():
    rendered = svgcore.element("text", "x", x=1, title=None)

    assert "title" not in rendered
    assert rendered == '<text x="1">x</text>'


def test_element_formats_floats_without_trailing_zeros():
    assert svgcore.element("rect", x=10.0, y=0.5, width=0.0) == (
        '<rect x="10" y="0.5" width="0"/>'
    )


def test_element_renders_a_custom_property_style_attribute():
    rendered = svgcore.element("rect", x=0, style=svgcore.paint("ch-1"))

    assert 'style="fill:var(--ch-1)"' in rendered


def test_element_renders_a_class_attribute():
    """`class` is a Python keyword, so it needs its own parameter name."""
    assert svgcore.element("rect", x=0, cls="mark") == '<rect class="mark" x="0"/>'


def test_element_puts_class_before_the_other_attributes():
    """Class first keeps the mark selector readable in the rendered source."""
    rendered = svgcore.element("rect", x=0, cls="mark", style=svgcore.paint("ch-1"))

    assert rendered.startswith('<rect class="mark" ')


# --- scales -------------------------------------------------------------------


def test_linear_scale_maps_the_domain_onto_the_range():
    scale = svgcore.linear((0.0, 10.0), (0.0, 100.0))

    assert scale(0.0) == pytest.approx(0.0)
    assert scale(5.0) == pytest.approx(50.0)
    assert scale(10.0) == pytest.approx(100.0)


def test_linear_scale_can_run_backwards_for_a_y_axis():
    scale = svgcore.linear((0.0, 10.0), (200.0, 0.0))

    assert scale(0.0) == pytest.approx(200.0)
    assert scale(10.0) == pytest.approx(0.0)


def test_linear_scale_with_a_zero_width_domain_pins_to_the_range_start():
    """Every value equal means every bar has zero length, not a ZeroDivisionError."""
    scale = svgcore.linear((0.0, 0.0), (0.0, 100.0))

    assert scale(0.0) == pytest.approx(0.0)


def test_linear_scale_extrapolates_outside_the_domain():
    scale = svgcore.linear((0.0, 10.0), (0.0, 100.0))

    assert scale(12.0) == pytest.approx(120.0)


# --- ticks --------------------------------------------------------------------


def test_nice_step_rounds_up_to_a_readable_number():
    assert svgcore.nice_step(3.0, count=5) == pytest.approx(1.0)
    assert svgcore.nice_step(8.0, count=5) == pytest.approx(2.0)
    assert svgcore.nice_step(100.0, count=5) == pytest.approx(20.0)
    assert svgcore.nice_step(184.0, count=5) == pytest.approx(50.0)


def test_nice_ceiling_rounds_the_top_of_the_axis_up_to_a_tick():
    assert svgcore.nice_ceiling(3.0, count=5) == pytest.approx(3.0)
    assert svgcore.nice_ceiling(184.0, count=5) == pytest.approx(200.0)


def test_ticks_run_from_zero_to_the_ceiling_in_even_steps():
    assert svgcore.ticks(3.0, count=5) == pytest.approx((0.0, 1.0, 2.0, 3.0))
    assert svgcore.ticks(8.0, count=5) == pytest.approx((0.0, 2.0, 4.0, 6.0, 8.0))


def test_ticks_cover_the_data_with_a_round_top():
    ticks = svgcore.ticks(184.0, count=5)

    assert ticks[0] == 0.0
    assert ticks[-1] == pytest.approx(200.0)
    assert ticks[-1] >= 184.0


def test_ticks_on_zero_data_are_just_the_origin():
    assert svgcore.ticks(0.0, count=5) == (0.0,)


def test_ticks_on_negative_or_invalid_input_do_not_crash():
    assert svgcore.ticks(-5.0, count=5) == (0.0,)


# --- number formatting --------------------------------------------------------


def test_fmt_trims_trailing_zeros():
    assert svgcore.fmt(70.0) == "70"
    assert svgcore.fmt(0.5) == "0,5"
    assert svgcore.fmt(0.0) == "0"


def test_fmt_honours_the_requested_precision():
    assert svgcore.fmt(66.666, 1) == "66,7"
    assert svgcore.fmt(66.666, 0) == "67"
    assert svgcore.fmt(1.0 / 3.0, 2) == "0,33"


def test_fmt_never_leaves_a_bare_trailing_separator():
    """The comma swap has to happen *after* the zeros are trimmed.

    Swapping first turns `70.00` into `70,00`, and trimming zeros off the end of
    that gives `70,` — a number that reads as broken on the page.
    """
    assert svgcore.fmt(70.0, 1) == "70"
    assert svgcore.fmt(9.0, 2) == "9"


def test_number_keeps_a_period_for_svg_geometry():
    """Display numbers are German; coordinates are not.

    `fmt` feeds `viewBox="0 0 720 236"` as well as the labels, and a `viewBox` of
    `0 0 720 236,5` is not valid SVG — the browser drops the whole chart.
    """
    assert svgcore.number(236.5) == "236.5"
    assert svgcore.number(720.0) == "720"
    assert svgcore.number(0.25) == "0.25"


def test_fmt_handles_a_missing_value():
    assert svgcore.fmt(None) == "—"


def test_share_carries_the_unit_and_trims_like_fmt():
    """A label says `37,5 %`, not `37,5` and not `37,50 %`."""
    assert svgcore.share(37.5) == "37,5 %"
    assert svgcore.share(100.0) == "100 %"


def test_share_rounds_to_one_decimal_by_default():
    """The chart and the table twin both call this; 17.391 must land the same both places."""
    assert svgcore.share(17.391) == "17,4 %"


def test_share_takes_its_precision_from_the_caller():
    assert svgcore.share(66.666, 0) == "67 %"


def test_share_on_a_missing_value_is_not_a_share():
    """A unit on an em dash would read as a measured zero."""
    assert svgcore.share(None) == "—"


# --- the palette contract -----------------------------------------------------


def test_paint_names_a_slot_rather_than_a_colour():
    assert svgcore.paint("ch-1") == "fill:var(--ch-1)"
    assert svgcore.paint("ch-3", "stroke") == "stroke:var(--ch-3)"


def test_paint_never_emits_a_literal_colour():
    for token in ("ch-1", "grid", "text-secondary"):
        assert "#" not in svgcore.paint(token)
