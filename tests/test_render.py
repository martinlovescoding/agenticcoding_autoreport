"""Slot substitution.

The contract with the design is two sigils and nothing else:

* `{{NAME}}` — escaped. Every dynamic string, because channel and specialty labels
  come from an untrusted export.
* `{{{NAME}}}` — raw. Only pre-rendered markup this program built itself: the SVGs
  and the tables.

A missing slot raises rather than rendering an empty hole. A report that silently
loses its headline number is worse than one that refuses to build.
"""

import pytest

from agenticcoding import render

# --- the two sigils -----------------------------------------------------------


def test_escaped_slot_is_substituted():
    assert render.render("<h1>{{TITLE}}</h1>", {"TITLE": "Q3 Review"}) == "<h1>Q3 Review</h1>"


def test_escaped_slot_neutralizes_markup_from_the_data():
    """A specialty label is a CSV cell; it must never become markup."""
    out = render.render("{{LABEL}}", {"LABEL": '<img src=x onerror="alert(1)">'})

    assert "<img" not in out
    assert "&lt;img" in out


def test_raw_slot_passes_markup_through():
    out = render.render("<figure>{{{CHART}}}</figure>", {"CHART": "<svg><rect/></svg>"})

    assert out == "<figure><svg><rect/></svg></figure>"


def test_raw_slot_is_not_escaped():
    out = render.render("{{{CHART}}}", {"CHART": '<text data-tip="a & b">x</text>'})

    assert 'data-tip="a & b"' in out


def test_triple_braces_are_not_mistaken_for_a_double():
    """`{{{X}}}` must not render as `{` + the escaped slot + `}`."""
    out = render.render("{{{X}}}", {"X": "<b>"})

    assert out == "<b>"


def test_both_sigils_can_appear_together():
    out = render.render("{{A}}|{{{B}}}", {"A": "<a>", "B": "<b>"})

    assert out == "&lt;a&gt;|<b>"


# --- failure is loud ----------------------------------------------------------


def test_a_missing_slot_raises():
    with pytest.raises(KeyError):
        render.render("{{TITLE}}", {})


def test_a_missing_raw_slot_raises():
    with pytest.raises(KeyError):
        render.render("{{{CHART}}}", {})


def test_extra_slots_are_harmless():
    """A caller may compute a value a given template does not use."""
    assert render.render("{{A}}", {"A": "1", "B": "2"}) == "1"


# --- comments are documentation, not markup -----------------------------------


def test_a_sigil_inside_a_comment_is_not_substituted():
    """The template documents its own slot syntax; that must not break the build."""
    out = render.render("<!-- a slot looks like {{TITLE}} --><p>hi</p>", {"TITLE": "x"})

    assert "{{" not in out


def test_comments_do_not_reach_the_rendered_page():
    out = render.render("<p>hi</p><!-- a note for whoever edits this -->", {})

    assert "a note for whoever edits this" not in out
    assert out == "<p>hi</p>"


def test_slots_in_ignores_comments():
    assert render.slots_in("<!-- {{TITLE}} -->{{BODY}}") == {"BODY"}


def test_a_raw_sigil_inside_a_comment_is_not_substituted():
    out = render.render("<!-- {{{CHART}}} -->", {})

    assert out == ""


# --- introspection, for the parity test --------------------------------------


def test_slots_in_finds_both_kinds():
    found = render.slots_in("{{A}} {{{B}}} {{C}}")

    assert found == {"A", "B", "C"}


def test_slots_in_ignores_ordinary_braces():
    assert render.slots_in("a { b } c") == set()


def test_slots_in_on_a_template_without_slots():
    assert render.slots_in("<p>static</p>") == set()


def test_render_leaves_no_sigils_behind():
    out = render.render("<p>{{A}}</p>{{{B}}}", {"A": "x", "B": "<i/>"})

    assert "{{" not in out
