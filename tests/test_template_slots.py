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
        charts.hero_trend(metrics.monthly_trend(SAMPLE)),
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
    """Every token's hex in one theme, dark layered over light as the cascade does.

    A committed single-theme design declares no dark scope at all, and every one of
    these tests then reads the light palette — because that is the palette such a page
    actually paints, in every viewer setting. Demanding a dark scope here would be
    these tests pinning a design decision, which `AGENTS.md` forbids: what the contract
    requires is that whichever themes the page *declares* are complete and readable,
    not that it declares two.
    """
    scopes = _scopes(template)
    if mode == "light":
        return scopes[LIGHT_SCOPE]
    return {**scopes[LIGHT_SCOPE], **{key: value for scope in DARK_SCOPES
                                      for key, value in scopes.get(scope, {}).items()}}


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
    """Counted by the chart class rather than by `<svg>`.

    A page may legitimately carry a decorative `<svg>` — an icon, a rule, the delivered
    design's wave under its hero panel — and counting `<svg>` would make that a false
    failure. What the contract promises is one chart element per analysis, plus the
    hero, so that is what is counted.
    """
    page = render.render(template, slots)

    assert page.count('class="chart"') == 4, "the hero plus one chart per analysis"


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


def test_the_two_dark_scopes_agree_with_each_other(template):
    """A token the media query moves but the stamp does not leaves the toggle half-lit.

    Either the page declares both dark scopes or it declares neither. Declaring one is
    the failure: the OS setting and the explicit toggle are the same theme, and a page
    that answers only one of them renders two different designs depending on which
    switch the reader touched. A single-theme design declares neither, and everything
    else here reads it as light — which is what it is.
    """
    scopes = _scopes(template)
    declared = [scopes.get(scope) for scope in DARK_SCOPES]

    assert (declared[0] is None) == (declared[1] is None), (
        f"only one dark scope is declared: {[scope for scope, body in
                                           zip(DARK_SCOPES, declared) if body is not None]}"
    )
    if declared[0] is not None:
        assert declared[0] == declared[1]


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


# The three inks every one of these pages writes body text with, and the names a design
# may give its surfaces. A design declares the surfaces it actually paints; this checks
# each text token against each of them, so a template only has to declare what it uses
# and neither design's palette is imposed on the other.
TEXT_TOKENS = ("text-primary", "text-secondary", "text-muted")
GROUND_TOKENS = ("bg", "card", "tile", "stone", "stone-light")

# The `report.html` design's own pairs — everything the templated markup actually puts
# together, including its two special surfaces: the row of tints a design may put behind
# text (`--stone`), and the dark green ground, which carries ink the page's own text
# tokens cannot read on. This is not a style guide; it is the list of pairs that exist
# in the page, so a pair can only be added here by adding it to the page.
PANEL_INK_ON_GROUND = (
    ("panel-fg", "green"),
    ("panel-fg", "green-deep"),
    ("panel-muted", "green"),
    ("panel-muted", "green-deep"),
    ("accent", "green"),
    ("accent", "green-deep"),
    ("green-deep", "accent"),
    ("tip-fg", "tip-bg"),
)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_text_token_is_readable_on_every_surface_the_design_declares(template, mode):
    """Computed, because the README asserted it and nothing checked it.

    It was not true. The delivered design's `--text-muted #6b6b6b` on `--stone #e5e3de`
    is 4.16:1 — a caption on the stone band was under the floor on every page the design
    produced, and no unit test could see it because no test multiplied the two tokens
    together. The fix belonged to the palette, not to the layout: the token moved to
    #616161 and the band stayed where the design put it.
    """
    tokens = palette(template, mode)
    grounds = [name for name in GROUND_TOKENS if name in tokens]

    assert "bg" in grounds and "card" in grounds, "a page that paints no ground at all"

    unreadable = [
        (ink, ground, round(contrast(tokens[ink], tokens[ground]), 2))
        for ink in TEXT_TOKENS
        for ground in grounds
        if contrast(tokens[ink], tokens[ground]) < 4.5
    ]

    assert not unreadable, f"{mode} mode paints text below 4.5:1 on: {unreadable}"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_panel_ink_and_the_tooltip_are_readable_on_their_own_grounds(mode):
    """The report's non-page surfaces: the green panel, its button, and the tooltip.

    These are checked against `report.html` alone. They are that design's surfaces, not
    a rule for every design — the starter page declares no green ground at all, and
    demanding one of it would be this suite pinning one design's palette, which is the
    thing the handoff contract exists to prevent.
    """
    tokens = palette(report.load_template(), mode)

    unreadable = [
        (ink, ground, round(contrast(tokens[ink], tokens[ground]), 2))
        for ink, ground in PANEL_INK_ON_GROUND
        if contrast(tokens[ink], tokens[ground]) < 4.5
    ]

    assert not unreadable, f"{mode} mode paints text below 4.5:1 on: {unreadable}"


def test_where_the_accent_is_used_as_text_it_can_be_read(template):
    """An accent is usually a fill or a mark, and a *text* colour only by accident.

    The report's accent is a lime: 8.35:1 on the green panel and 1.70:1 on white. Used
    as link text on the page's own ground it would be invisible, and the failure is
    silent — the page renders, the text is in the DOM, and nobody can read it. Such a
    design must therefore scope every rule that paints text with the accent to a green
    ground, which is the class `.panel` the header, the hero and the footer all carry.

    A design whose accent *is* readable as body text — the starter's dark blue is
    ~7:1 — is free to use it unscoped. The rule is readability, not the selector, so
    this passes either way and only fails the pairing that is actually unreadable.
    """
    css = template.split("<style>", 1)[1].split("</style>", 1)[0]
    tokens = palette(template, "light")
    on_the_page = contrast(tokens["accent"], tokens["bg"]) >= 4.5

    unscoped = [
        selector
        for selector, body in _blocks(css)
        if re.search(r"(?:^|;)\s*color:\s*var\(--accent\)", body)
        and not re.search(r"(?:^|[\s,>])\.panel(?:[\s,>.:{]|$)", selector)
    ]

    assert on_the_page or not unscoped, (
        f"--accent is {round(contrast(tokens['accent'], tokens['bg']), 2)}:1 on --bg, "
        f"so these rules would paint unreadable text: {unscoped}"
    )


def test_the_page_shell_is_reachable_without_the_installed_package(monkeypatch):
    """A repo checkout must be able to render even if the package data did not ship."""
    monkeypatch.setattr(report, "_packaged_template", lambda name: None)

    assert "<style>" in report.load_template()
