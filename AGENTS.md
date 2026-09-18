# Working on this repo

*Named `AGENTS.md`, the filename agents read. If you were looking for `agent.md`, it is
this file — say the word and it gets renamed.*

A report generator: one CSV in, one self-contained `report.html` out. Standard library
only, no runtime dependencies, `pytest` the only dev dependency, charts hand-built as
inline SVG.

Read `docs/architecture.md` before a structural change — it explains the shape and which
decisions are load-bearing. This file is the operational half: how to run it, and what
must not break.

---

## Commands

```bash
uv sync                                  # install (dev deps included)

uv run pytest                            # 328 tests, ~13s
uv run pytest tests/test_clean.py -q     # one file
uv run pytest -k heatmap                 # one name

# run it
uv run python -m agenticcoding generate --rows 200 --out data/raw_activities.csv
uv run python -m agenticcoding report   --input data/raw_activities.csv --out report.html
open report.html
```

`--as-of YYYY-MM-DD` is the reference date for the "date is in the future" rule. **Pass it
in tests** — it is what makes a report reproducible on a later day.

The five `test_layout.py` tests open the rendered page in real Chrome. They skip when no
browser is installed, so `328 passed` and `323 passed, 5 skipped` are both healthy.

---

## Non-negotiables

Each of these is a real failure that has happened, not a style preference. The test that
catches it is named so you can watch it fail.

| Rule | Why | Caught by |
|---|---|---|
| **No runtime dependency, ever** | The offline guarantee is the point. No pandas, no Jinja2, no chart library — not even a small one. | `test_report_pages_the_generated_csv_without_network_references` |
| **Charts name palette tokens, never colours** | It is the mechanism of the design handoff. `fill="var(--ch-3)"`, never `fill="#2a78d6"`. | `test_the_template_defines_every_palette_slot_the_charts_name` |
| **CSV values go through `{{NAME}}`, never `{{{NAME}}}`** | Everything out of the CSV is untrusted. Raw slots are for markup this program rendered itself. | review — see `report._bold()` for the pattern |
| **Keep the slot vocabulary in step, both directions** | A renamed slot renders a hole; an unused slot is a value that stopped reaching the page. | `test_every_slot_the_template_asks_for_is_supplied`, `test_every_slot_supplied_is_used_by_the_template` |
| **Every dark token in *both* scopes** | The unstamped document is what most viewers see; a token defined only behind a media query leaves them with no colour. | `test_both_dark_scopes_declare_the_same_tokens` |
| **Keep `minmax(0, 1fr)` and `min-width: 0`** | A grid track floors at its items' min-content width and so does a grid item — drop either and a `nowrap` cell widens the whole page. | `test_the_page_does_not_scroll_sideways_on_a_phone` |
| **A chart keeps the surface its palette was validated against** | The phone floor and the light-in-dark-band card are both deliberate. | `test_every_chart_stays_legible_on_a_phone` |
| **Count every row the pipeline drops** | The counters are the data basis panel on the page. A drop that is not counted is a lie by omission. | `test_clean.py` |

---

## Test-driven development

**No production code without a failing test first.** Write the test, watch it fail for the
right reason, then write the code. A test that passed the first time you ran it has proved
nothing — you never saw it catch anything.

**Adding a test to existing code** — the case that comes up most here — has no natural red
step, so use a **mutation check**:

1. Write the test.
2. Break the production code the way the test claims to catch.
3. Watch it go red, and read the failure: does it name the thing you broke?
4. Restore. Watch it go green.

This is not ceremony. `test_every_step_of_the_ramp_is_readable_on_its_own_cell` exists
because a mutation check showed that the sample dataset never reaches ramp step 4, so an
unreadable ink there passed every check in the file. Mutation checks are how this suite
found that.

**A test may not pin a design detail.** No asserting on a class name, a colour, or a
heading's wording — that turns every design swap into a suite of false failures. Assert on
the page's *words*, as `test_report_carries_the_cleaned_row_count_into_the_page` does.

---

## Where to change what

| To change… | Touch |
|---|---|
| A channel, a specialty, a threshold, a synonym | `schema.py`, then add the token to the template. Nothing else. |
| What a number means | `metrics.py` (pure functions over rows; returns dataclasses) |
| What a chart looks like *structurally* | `charts.py` — but colour comes from tokens, so recolouring is a template edit |
| Which words/columns reach the page | `report.py` — the view model. Keep the spec and the template in step. |
| The design | `src/agenticcoding/templates/report.html` — start from `design-template.html` beside it |
| The cleaning policy | `clean.py` — and add the stage to `_STAGE_LABELS`, because the label is user-visible |
| Argument parsing, exit codes | `cli.py` — exit 0 ok, 2 usage, 1 bad input |

Only `report.py` knows both what a number *means* and what the template *calls* it. That
is the seam that makes the design a template edit. Don't weld it shut by importing
`charts` into `metrics`, or `report` into `charts`.

---

## Definition of done

1. `uv run pytest` — green, no skips you did not expect, no warnings.
2. New behaviour has a test you watched fail.
3. `report.html` rendered and **looked at** in a browser — light, dark, and narrow. A green
   suite does not mean the page is right: the validator checks colour, not layout, and
   nobody's unit test sees a label collision.
4. If a number on the page changed, the prose that describes it still reads true — the
   takeaways and the data basis panel are generated, but the static captions in the
   template are not.
5. README updated if a command, a flag, a count or a known limitation moved.

---

## Gotchas

- **HTML comments in the template are stripped before substitution.** Document slot syntax
  inside `<!-- -->` and it ships as nothing. Leave the comment markers off and the
  documentation renders *as page text* and every name in it becomes a `KeyError`. This
  happened.
- **`uv_build` package data is not guaranteed.** `report.load_template()` falls back to
  reading the file beside the module. Both paths must work; there is a test for it.
- **A CSS variable as an SVG presentation attribute renders black in Firefox.**
  `style="fill:var(--ch-1)"` is valid; `fill="var(--ch-1)"` is not. `svgcore.paint()`
  emits the declaration form for this reason.
- **`_scopes()` collapses duplicate blocks.** All light tokens must stay in ONE `:root`
  block and each dark scope in ONE block, or a later block overwrites an earlier one and
  the palette silently loses tokens.
- **Chrome headless clamps its window to ~500 CSS px**, so a true 400px viewport needs an
  iframe (`test_layout.py` does this). Fragment scrolling (`file://…#anchor`) is unreliable
  in `--headless=new`.

---

## What not to do

- Don't add a dependency. If a chart needs something, `svgcore.py` is where primitives go.
- Don't un-inline the CSS or the JS into separate files — the page must be one file.
- Don't change a palette token's *name*. The names are the contract between `charts.py`
  and the design; change the values freely.
- Don't hand-edit a rendered `report.html`. It is generated output — edit the template and
  re-render, or the next render erases your change.
- Don't publish anything anywhere without asking. The target repo is public.
