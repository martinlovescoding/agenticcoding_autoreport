"""Slot substitution — the boundary between the pipeline and the design.

The template owns every static word, every heading and all of the styling. Python
supplies only the values. That split is the whole point of this module: the design
handoff is a template edit, and nothing here has to change when it arrives.

Two sigils, and the difference between them is a security boundary:

* `{{NAME}}` — escaped. Everything that came out of the CSV: channel names, specialty
  labels, rep and territory strings. They are untrusted input and must never be able
  to become markup.
* `{{{NAME}}}` — raw. Only markup this program rendered itself: the chart SVGs and
  the table twins.

A third rule keeps the first two from being fragile: **HTML comments are neither
substituted nor shipped.** The template documents its own slot syntax in a comment,
and a designer will annotate theirs; without this, either would be read as a slot.
Comments are stripped from the output, so nothing the designer left for themselves
reaches the page.

A slot the template asks for but the view model did not supply raises `KeyError`
rather than rendering an empty hole. A report that silently loses its headline number
is worse than one that refuses to build.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .svgcore import esc

# One pattern for all three cases, so `slots_in` and `render` can never disagree about
# what a slot is. Comments come first: at any position a comment wins over a sigil
# inside it. Triple braces are tried before double, so `{{{X}}}` is one raw slot rather
# than a literal `{` followed by an escaped one.
_TOKEN = re.compile(
    r"(?P<comment><!--.*?-->)"
    r"|(?P<raw>\{\{\{(?P<raw_name>[A-Za-z_][A-Za-z0-9_]*)\}\}\})"
    r"|(?P<escaped>\{\{(?P<escaped_name>[A-Za-z_][A-Za-z0-9_]*)\}\})",
    re.DOTALL,
)


def slots_in(template: str) -> set[str]:
    """Every slot name a template references, of either kind, outside its comments.

    Used by the parity test: the names the design asks for must be exactly the names
    the view model supplies, so a renamed slot fails loudly instead of quietly
    rendering nothing.
    """
    return {
        match.group("raw_name") or match.group("escaped_name")
        for match in _TOKEN.finditer(template)
        if match.group("comment") is None
    }


def render(template: str, slots: Mapping[str, str]) -> str:
    """Substitute `slots` into `template`, dropping HTML comments.

    Raises `KeyError` for a slot with no value. Extra values are ignored: a caller may
    compute something a particular template does not use.
    """

    def substitute(match: re.Match[str]) -> str:
        if match.group("comment") is not None:
            return ""
        raw = match.group("raw_name")
        if raw is not None:
            return str(slots[raw])
        return esc(slots[match.group("escaped_name")])

    return _TOKEN.sub(substitute, template)
