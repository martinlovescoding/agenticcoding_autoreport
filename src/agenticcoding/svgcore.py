"""Primitives for hand-built inline SVG.

Charts are composed in `charts.py`; everything geometric and everything dangerous
lives here, so six charts do not become six copies of the same axis code.

Three rules this module exists to enforce:

1. **Escape everything.** `esc` runs on text content *and* attribute values, because
   channel and specialty labels come from an untrusted export.
2. **Colour is a slot, not a value.** `paint` emits `fill:var(--ch-1)`, never `#2a78d6`.
   That single indirection is what makes a design swap a template edit. It also has to
   live in a `style` attribute — `fill="var(--ch-1)"` as a presentation attribute is
   invalid and renders black in Firefox.
3. **No output without a test.** Every function here is asserted in `test_svgcore.py`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from xml.sax.saxutils import escape as _xml_escape

# `escape` handles & < >; attribute values need the quotes too.
_QUOTES = {'"': "&quot;", "'": "&apos;"}

# Rounding candidates for an axis step, in ascending order. 2.5 earns its place:
# it turns 0–25 into 0/5/10/15/20/25 rather than 0/10/20/30.
_STEPS: tuple[float, ...] = (1.0, 2.0, 2.5, 5.0, 10.0)

# What `fmt` shows for a value that is not there. An em dash, not "0" or "N/A" —
# a missing average must never read as a measured zero.
MISSING = "—"


# --- escaping -----------------------------------------------------------------


def esc(value: object) -> str:
    """Escape a value for XML text content *and* attribute values.

    One function for both contexts: the escaping needed for text content is a subset
    of what attributes need, so a single conservative version cannot be used wrongly.
    """
    if value is None:
        return ""
    return _xml_escape(str(value), _QUOTES)


# --- the element builder ------------------------------------------------------


def _attr(value: object) -> str:
    """Format one attribute value. Floats lose their trailing zeros: `10.0` → `10`."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return number(value)
    return str(value)


def element(tag: str, text: object = None, cls: str | None = None, **attributes: object) -> str:
    """Build one SVG element, escaping both its attributes and its text.

    Attributes whose value is `None` are omitted rather than rendered as `None`, so
    callers can pass an optional tooltip or title straight through. `class` arrives
    through `cls` because it is a Python keyword; it is emitted first so the mark
    selector is easy to find in the rendered source.
    """
    rendered = "" if cls is None else f' class="{esc(cls)}"'
    rendered += "".join(
        f' {name}="{esc(_attr(value))}"'
        for name, value in attributes.items()
        if value is not None
    )
    if text is None:
        return f"<{tag}{rendered}/>"
    return f"<{tag}{rendered}>{esc(text)}</{tag}>"


# --- scales -------------------------------------------------------------------


def linear(
    domain: tuple[float, float], out: tuple[float, float]
) -> Callable[[float], float]:
    """A linear scale from `domain` onto `out`. May run backwards (a y axis does).

    A zero-width domain pins every value to the start of the output range: a channel
    whose bars are all the same length gets zero-length bars, not a ZeroDivisionError.
    """
    low, high = domain
    out_low, out_high = out
    span = high - low

    def scale(value: float) -> float:
        if span == 0:
            return out_low
        return out_low + (value - low) * (out_high - out_low) / span

    return scale


# --- ticks --------------------------------------------------------------------


def nice_step(span: float, count: int = 5) -> float:
    """The smallest readable step that covers `span` in at most `count` intervals."""
    if span <= 0 or count <= 0:
        return 1.0
    raw = span / count
    magnitude = 10.0 ** math.floor(math.log10(raw))
    normalized = raw / magnitude
    for step in _STEPS:
        if normalized <= step:
            return step * magnitude
    return 10.0 * magnitude


def nice_ceiling(value: float, count: int = 5) -> float:
    """`value` rounded up to a whole number of `nice_step` intervals."""
    if value <= 0:
        return 0.0
    step = nice_step(value, count)
    return math.ceil(value / step) * step


def ticks(max_value: float, count: int = 5) -> tuple[float, ...]:
    """Tick values from zero to a round top that still covers the data.

    The top is rounded *up*, never truncated: an axis that stops at the largest bar
    makes that bar unreadable and implies the scale ends there.
    """
    if max_value <= 0:
        return (0.0,)
    step = nice_step(max_value, count)
    intervals = int(round(nice_ceiling(max_value, count) / step))
    return tuple(index * step for index in range(intervals + 1))


# --- number formatting --------------------------------------------------------


def _strip(text: str) -> str:
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def number(value: float, decimals: int | None = None) -> str:
    """Format a number for **SVG geometry**, where the separator must stay a period.

    `viewBox="0 0 720 236.5"` is valid; `0 0 720 236,5` is not, and a browser that
    cannot parse a `viewBox` drops the entire chart rather than one label. Geometry
    therefore never goes through `fmt` — this is the function for it, and `_attr`
    is built on it so the trailing-zero rule lives in exactly one place.
    """
    return _strip(f"{value:.{decimals}f}" if decimals is not None else f"{value:.2f}")


def fmt(value: float | None, decimals: int | None = None) -> str:
    """Format a number for a **label**, German-style. `None` becomes an em dash.

    With `decimals` unset, a value shows at most two decimals and only as many as it
    needs: `70.0` → `70`, `0.5` → `0,5`, `1/3` → `0,33`.

    The comma is swapped in *after* `number` has trimmed the trailing zeros: the
    other order turns `70.00` into `70,00` and then trims it to `70,`, which is what
    a reader would see on the page.
    """
    if value is None:
        return MISSING
    return number(value, decimals).replace(".", ",")


def share(value: float | None, decimals: int = 1) -> str:
    """Format a percentage. Separated from `fmt` so the unit lives in one place."""
    return MISSING if value is None else f"{fmt(value, decimals)} %"


# --- the palette contract -----------------------------------------------------


def paint(token: str, prop: str = "fill") -> str:
    """A CSS declaration binding an SVG property to a design-system slot.

    Returns the *declaration*, not the attribute, so it composes:
    `element("rect", style=paint("ch-1"))`.
    """
    return f"{prop}:var(--{token})"
