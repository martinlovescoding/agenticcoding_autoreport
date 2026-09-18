"""The design-handoff safety net.

The template is the one file a designer replaces. When they do, two things must
still line up:

* **Slot parity** — every slot the template asks for is a slot the view model
  supplies, and vice versa. A renamed slot fails here instead of rendering a hole.
* **No leftover sigils** — a rendered report contains no `{{`, so nothing the
  designer wrote was silently left unsubstituted.

These tests are the reason the handoff is a template edit and not a code change.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from agenticcoding import charts, clean, metrics, render, report
from conftest import SAMPLE

LIGHT_SCOPE = ":root"
DARK_SCOPES = (':root:not([data-theme="light"])', ':root[data-theme="dark"]')

# Both templates, held to the same contract. `report.html` is what the tool renders;
# `design-template.html` is the starter a designer restyles. The starter is only worth
# handing over if it is complete, so it is checked exactly as the live design is — by
# the same tests, not by a second set that would drift out of step with them.
TEMPLATES = ("report.html", "design-template.html")


def fragments() -> tuple[str, ...]:
    """Every chart the report renders, as emitted."""
    return (
        charts.channel_bars(metrics.channel_mix(SAMPLE)),
        charts.monthly_columns(metrics.monthly_trend(SAMPLE)),
        charts.specialty_heatmap(metrics.specialty_matrix(SAMPLE)),
    )


def quality() -> clean.QualityReport:
    return clean.QualityReport(
        rows_in=len(SAMPLE),
        rows_out=len(SAMPLE),
        notes=tuple(
            clean.QualityNote(key=key, label=label, count=0)
            for key, label in clean._STAGE_LABELS
        ),
    )


def _blocks(css: str) -> list[tuple[str, str]]:
    """`(selector, body)` for every block in a stylesheet, nested ones included."""
    found: list[tuple[str, str]] = []
    cursor = 0
    while (opening := css.find("{", cursor)) != -1:
        depth, end = 1, opening + 1
        while depth and end < len(css):
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        body = css[opening + 1 : end - 1]
        selector = css[cursor:opening].rsplit("}", 1)[-1].rsplit("*/", 1)[-1].strip()
        found.append((selector, body))
        found.extend(_blocks(body))
        cursor = end
    return found


def _scopes(template: str) -> dict[str, dict[str, str]]:
    """The literal hex each token resolves to, per theme scope."""
    css = template.split("<style>", 1)[1].split("</style>", 1)[0]
    return {
        selector: dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", body))
        for selector, body in _blocks(css)
    }


def palette(template: str, mode: str) -> dict[str, str]:
    """Every token's hex in one theme, dark layered over light as the cascade does."""
    scopes = _scopes(template)
    if mode == "light":
        return scopes[LIGHT_SCOPE]
    return {**scopes[LIGHT_SCOPE], **{key: value for scope in DARK_SCOPES
                                      for key, value in scopes[scope].items()}}


def _luminance(colour: str) -> float:
    channels = [int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    """The WCAG contrast ratio. 4.5 is the floor for body-sized text."""
    high, low = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _ink_token(element: ET.Element, css: str) -> str | None:
    """The `--token` an element paints its text with: inline first, then a class rule."""
    style = element.get("style") or ""
    if style.startswith("fill:var("):
        return style.removeprefix("fill:var(--").removesuffix(")")
    found = None
    for name in (element.get("class") or "").split():
        match = re.search(rf"\.{name}\s*\{{[^}}]*fill:\s*var\(--([a-z0-9-]+)\)", css)
        if match:
            found = match.group(1)
    return found


def _value_labels(template: str, fragment: str) -> list[tuple[str, str]]:
    """`(cell token, ink token)` for every value written inside a heatmap cell."""
    css = template.split("<style>", 1)[1].split("</style>", 1)[0]
    pairs: list[tuple[str, str]] = []
    cell: str | None = None
    for element in ET.fromstring(f"<svg>{fragment}</svg>").iter():
        if "cell-value" not in (element.get("class") or ""):
            style = element.get("style") or ""
            if style.startswith("fill:var("):
                cell = style.removeprefix("fill:var(--").removesuffix(")")
            continue
        ink = _ink_token(element, css)
        if ink and cell:
            pairs.append((cell, ink))
    return pairs


@pytest.fixture(params=TEMPLATES)
def template(request) -> str:
    return report.load_template(request.param)


@pytest.fixture
def slots() -> dict[str, str]:
    return report.build_slots(
        SAMPLE, quality(), source_file="data/raw_activities.csv", generated_at="18 September 2026"
    )


@pytest.mark.parametrize("name", TEMPLATES)
def test_the_template_can_be_loaded(name):
    """`uv_build` package data is not guaranteed, so this is the canary for it.

    Both files are package data, so both are checked: a design template that does
    not ship is a handoff that arrives as a missing file.
    """
    assert report.load_template(name) == (
        Path(report.__file__).resolve().parent / "templates" / name
    ).read_text("utf-8")


def test_the_design_template_is_not_the_rendered_one():
    """They are separate files. A designer restyling the starter must not be
    quietly restyling the report the pipeline produces."""
    assert report.load_template() != report.load_template("design-template.html")


def test_every_slot_the_template_asks_for_is_supplied(template, slots):
    missing = render.slots_in(template) - set(slots)

    assert not missing, f"the template asks for slots nothing supplies: {sorted(missing)}"


def test_every_slot_supplied_is_used_by_the_template(template, slots):
    """An unused slot is a value that silently stopped reaching the page."""
    unused = set(slots) - render.slots_in(template)

    assert not unused, f"the view model computes slots the template ignores: {sorted(unused)}"


def test_the_template_uses_both_sigils(template):
    """Raw slots are the only way pre-rendered SVG and tables reach the page."""
    assert "{{{" in template, "no raw slot — the charts cannot reach the page"
    assert render.slots_in(template)


def test_rendering_the_template_leaves_no_sigils(template, slots):
    assert "{{" not in render.render(template, slots)


def test_the_rendered_page_carries_the_charts(template, slots):
    page = render.render(template, slots)

    assert page.count("<svg") == 3, "one chart per analysis"


def test_the_rendered_page_carries_a_table_per_analysis(template, slots):
    page = render.render(template, slots)

    assert page.count("<table") >= 4, "three analysis twins plus the quality ledger"


def test_the_template_defines_every_palette_slot_the_charts_name(template, slots):
    """`paint` emits `var(--ch-3)`; a token the template never defines renders black."""
    referenced = set()
    for fragment in fragments():
        for token in fragment.split("var(--")[1:]:
            referenced.add(token.split(")")[0])

    undefined = {token for token in referenced if f"--{token}:" not in template}

    assert not undefined, f"charts name palette slots the template never defines: {sorted(undefined)}"


def test_the_template_styles_every_class_the_charts_emit(template, slots):
    """A class with no rule is a label that renders in the wrong ink."""
    emitted = set()
    for fragment in fragments():
        for chunk in fragment.split('class="')[1:]:
            emitted.update(chunk.split('"')[0].split())

    unstyled = {name for name in emitted if f".{name}" not in template}

    assert not unstyled, f"charts emit classes the template never styles: {sorted(unstyled)}"


def test_both_dark_scopes_declare_the_same_tokens(template):
    """A token the media query moves but the stamp does not leaves the toggle half-lit."""
    scopes = _scopes(template)

    assert scopes[DARK_SCOPES[0]] == scopes[DARK_SCOPES[1]]


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_heatmap_value_is_legible_on_the_cell_under_it(template, mode):
    """The ink flip is a colour decision, so it is computed, not eyeballed.

    The ramp is reversed for the dark surface — the deepest value is the *lightest*
    cell there. An ink chosen by ramp depth instead of by cell colour therefore lands
    white-on-pale-blue in dark mode: a ratio of 1.5:1, invisible in a screenshot.
    """
    tokens = palette(template, mode)
    pairs = _value_labels(template, charts.specialty_heatmap(metrics.specialty_matrix(SAMPLE)))

    assert pairs, "no heatmap value labels found — the parser stopped matching"
    unreadable = [
        (cell, ink, round(contrast(tokens[ink], tokens[cell]), 2))
        for cell, ink in pairs
        if contrast(tokens[ink], tokens[cell]) < 4.5
    ]

    assert not unreadable, f"{mode} mode is unreadable on: {unreadable}"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_step_of_the_ramp_has_an_ink_defined_for_it(template, mode):
    """A step with no ink token falls back to `fill` unset and renders black."""
    tokens = palette(template, mode)

    missing = [step for step in charts.SEQUENTIAL if f"{step}-ink" not in tokens]

    assert not missing, f"{mode} mode defines no ink for {missing}"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_step_of_the_ramp_is_readable_on_its_own_cell(template, mode):
    """Every step, not only the ones today's sample happens to reach.

    The heatmap test above reads the cells this dataset produced, and a small
    dataset does not span the ramp: with the fixture below, step 4 is never drawn,
    so an unreadable ink on step 4 passed every check in this file. The steps are
    a closed set, so they are checked as one.
    """
    tokens = palette(template, mode)

    unreadable = [
        (step, round(contrast(tokens[f"{step}-ink"], tokens[step]), 2))
        for step in charts.SEQUENTIAL
        if contrast(tokens[f"{step}-ink"], tokens[step]) < 4.5
    ]

    assert not unreadable, f"{mode} mode ramp inks are unreadable on: {unreadable}"


def test_the_page_shell_is_reachable_without_the_installed_package(monkeypatch):
    """A repo checkout must be able to render even if the package data did not ship."""
    monkeypatch.setattr(report, "_packaged_template", lambda name: None)

    assert "<style>" in report.load_template()
