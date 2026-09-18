# Architecture

How the report generator is put together, and why it is put together that way.

This is the document to read before changing anything structural. The README says what
the tool does; `AGENTS.md` says how to work on it; this says how it is shaped and which
decisions are load-bearing.

---

## 1 · The job

One CSV in, one `report.html` out. The CSV is a raw CRM export of pharma field-force
activity; the page is a snapshot with three analyses, each a chart and its table twin,
plus a panel that accounts for every row the pipeline dropped.

The shape of the system follows from five constraints, and every decision below is
traceable to one of them:

| Constraint | Consequence |
|---|---|
| **Standard library only** | No pandas, no matplotlib, no Jinja2. Arithmetic in `statistics`, charts as hand-built SVG strings, templating in 60 lines. |
| **The page is one file, offline** | No CDN, no web font, no chart library. Everything the page needs is inlined, including its CSS and its tooltip script. |
| **The design is handed over, not coded** | Python supplies values, never markup. The design lives in one template file, and swapping it is a template edit — not a code change. |
| **A report is a snapshot** | No server, no database, no config file, no state. Same input and same `--as-of` gives the same bytes. |
| **A wrong number is worse than no number** | Nothing is imputed. Every drop is counted and shown. A slot the view model cannot fill raises instead of rendering a hole. |

---

## 2 · Data flow

One direction, no cycles. Nothing downstream is ever read back upstream.

```
  raw CSV  ──►  generate.py ──►  data/raw_activities.csv
  (real export)   (stand-in)              │
                                          ▼
                                   ┌─────────────┐
                                   │  clean.py   │  ordered, idempotent,
                                   │             │  counted per stage
                                   └──────┬──────┘
                            kept rows ────┤──── QualityReport
                                          │        (rows_in, rows_out, notes)
                     ┌────────────────────┘
                     ▼
              ┌─────────────┐
              │ metrics.py  │   channel_mix · monthly_trend ·
              │             │   specialty_matrix · kpis
              └──────┬──────┘
                     │  ChannelMix, MonthlyTrend, SpecialtyMatrix, Kpis
        ┌────────────┴────────────┐
        ▼                         ▼
  ┌───────────┐            ┌──────────────┐
  │ charts.py │            │  report.py   │◄─── the design's slot vocabulary
  │           │            │  (view model)│
  └─────┬─────┘            └──────┬───────┘
        │ SVG fragments           │  dict[str, str] — every value pre-formatted
        └────────────┬────────────┘
                     ▼
              ┌─────────────┐        templates/report.html
              │ render.py   │◄──────  (the design: {{escaped}} / {{{raw}}})
              └──────┬──────┘
                     ▼
              ┌─────────────┐
              │ report.py   │  wraps the fragment in the page shell
              │  .document  │
              └──────┬──────┘
                     ▼
                report.html
```

The two arrows into `render` are the whole architecture in one picture: **`charts.py` and
the template never meet.** A chart knows its palette as token *names* (`--ch-3`), and the
template is the only file that knows what colour that is. That is what makes the design
swappable without touching the chart code, and what makes the palette checkable by
reading the template's own CSS.

---

## 3 · The modules

| Module | Lines | Imports | Responsibility |
|---|---:|---|---|
| `schema.py` | 250 | — | The vocabulary: 7 channels, specialties, synonym tables, plausibility thresholds, the frozen `Interaction` row, and the display label tables (`MONTHS_SHORT`, `SPECIALTY_LABELS`). |
| `svgcore.py` | 189 | — | Chart primitives: `esc`, `linear`, `nice_step`, `ticks`, `number`, `fmt`, `share`, `element`, `paint`. No chart knowledge. |
| `clean.py` | 309 | `schema` | The ordered cleaning pipeline, per-stage counters, `QualityReport`, CSV read/write. |
| `generate.py` | 297 | `schema` | A synthetic, seed-reproducible, deliberately dirty export. A stand-in for a real one. |
| `metrics.py` | 234 | `schema` | Aggregation: `channel_mix`, `monthly_trend`, `specialty_matrix`, `kpis`. Pure functions over rows. |
| `render.py` | 74 | `svgcore` | Slot substitution: the two sigils, comment stripping, `KeyError` on a missing slot. |
| `charts.py` | 443 | `metrics` `schema` `svgcore` | Four charts as SVG strings: the hero monthly total, then one per analysis. Names colour tokens, never colours. |
| `report.py` | 385 | `charts` `clean` `metrics` `render` `schema` `svgcore` | The view model: metrics → slots. Also the takeaways, the table twins and the page shell. |
| `cli.py` | 134 | `clean` `generate` `report` | `generate` and `report`, argument parsing, exit codes. |
| `__main__.py` | 8 | `cli` | `python -m agenticcoding`. |

The dependency graph is a DAG with four clean layers:

```
  schema   svgcore                 ← nothing depends on anything
     │        │
  clean  generate  metrics   render
     │              │          │
     └──────► charts ──────────┘
                 │
              report                    ← the only module that knows
                 │                         both the numbers and the design
                cli
```

**The layer rule:** a module may import only from the layers above it. `metrics.py` must
never import `charts.py`; `charts.py` must never import `report.py`. The one module
allowed to know both what a number *means* and what the template *calls* it is
`report.py` — that is precisely what makes it the seam. Breaking the rule elsewhere welds
the design to the data, and the handoff stops being a template edit.

---

## 4 · The two contracts

### 4.1 The slot contract (`render.py` + `report.py`)

The template is a fill-in-the-blanks document with two sigils, and the difference between
them is a **security boundary**:

| Sigil | Meaning | Who may use it |
|---|---|---|
| `{{NAME}}` | escaped text | Anything, including values that came out of the CSV |
| `{{{NAME}}}` | raw HTML | Only markup this program rendered itself: chart SVGs, table twins, takeaways |

Everything from the CSV is untrusted input. A rep name, a product name or a specialty
label that contains `<script>` must render as text; only fragments the program built may
carry markup. So the rule is not "escape where it looks risky" — it is that every value's
provenance decides its sigil, and `report._bold()` is the one place that escapes a label
going into a sentence that itself travels through a raw slot.

Three more rules make the contract hold:

- **HTML comments are neither substituted nor shipped.** The template documents its own
  slot syntax in a comment at the top; `render` strips it, so nothing unsubstituted leaks
  and no `{{NAME}}` inside documentation becomes a `KeyError`.
- **A missing slot raises.** `render(template, slots)` raises `KeyError` rather than
  substituting an empty string. A report that silently loses its headline number is worse
  than one that refuses to build.
- **Slot parity runs in both directions.** Every slot the template asks for is supplied,
  *and* every slot the view model computes is used. The second direction catches a value
  that quietly stopped reaching the page.

### 4.2 The palette contract (`charts.py` + the template's CSS)

No chart ever names a colour. A mark carries `style="fill:var(--ch-3)"`, and the template
defines what `--ch-3` is. There are two families:

| Family | Job | Rule |
|---|---|---|
| `--ch-1` … `--ch-7` | **identity** — one per channel | Fixed order, in schema order. Colour follows the entity, never the rank: `ch-4` is Rep Email wherever it ranks, so a change in position never repaints the survivors. |
| `--seq-1` … `--seq-7` | **magnitude** — mean engagement | One hue, light to dark. Never the categorical slots. Each step carries a `-ink` token for the text inside its own cell. |

Text never wears a series colour. A label's fill is only ever an `-ink` token, chosen for
readability against the surface behind it, which is why the ink is not inherited from the
design's palette — the design's greys were measurably below the 4.5:1 body-text floor.
The same reasoning re-points the text tokens inside `.panel`: the page's `--text-primary`
on the dark green ground is 1.2:1, so the panel states its own ink once and every element
inside it inherits a readable default.

**A theme is declared, not implied.** Two shapes are legal, and both are checked:

- **Three states** (the starter's shape). The bare `:root` block holds the complete light
  palette, because an unstamped document is what most viewers see and only
  `prefers-color-scheme` separates light from dark. The dark palette is then declared
  twice — under `@media (prefers-color-scheme: dark)` guarded as
  `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]` — so an
  explicit choice beats the system in both directions. Dark is *selected*, not flipped: it
  has its own step values, validated against the dark surface.
- **One committed state** (the live design's shape). A design that deliberately commits to
  a single look may declare no dark scope at all. Every check then reads it as light,
  because that is the palette it paints in every viewer setting.

Declaring *one* dark scope is the failure, and the only one: the OS preference and the
explicit toggle are the same theme, so a page that answers one and not the other renders
two different designs from one switch.

**`color-scheme` follows the rendered page, not the design's intent.**
`report.document` reads the rendered fragment back and emits `light dark` only if the page
actually carries a dark scope. A light-only page that promises `light dark` hands the
reader dark scrollbars and dark form controls over a light background — the promise and the
paint disagree, and nothing else notices.

---

## 5 · Invariants and what enforces them

Each row is a property the system must not lose. The last column names the test that
fails when it does — the point being that no invariant here relies on anyone remembering
it.

| # | Invariant | Why it matters | Enforced by |
|---|---|---|---|
| 1 | Every slot the template asks for is supplied, and every slot supplied is used | A renamed slot renders a hole or silently drops a value | `test_template_slots.py::test_every_slot_*` (both directions) |
| 2 | A rendered report contains no `{{` | An unsubstituted slot is a visible artifact in the page | `test_rendering_the_template_leaves_no_sigils` |
| 3 | Every palette token a chart names is defined by the template | `var(--ch-3)` with no definition renders **black**, in every theme the page declares | `test_the_template_defines_every_palette_slot_the_charts_name` |
| 4 | Every class a chart emits has a rule | An unstyled label renders in the wrong ink | `test_the_template_styles_every_class_the_charts_emit` |
| 5 | A design declares both dark scopes or neither, and if both then identically | A token one scope moves and the other does not leaves the toggle half-lit; declaring one and not the other renders two designs from one switch. Declaring neither is a valid single-theme design, and every check then reads it as light — which is what it paints | `test_the_two_dark_scopes_agree_with_each_other` |
| 6 | Every heatmap value clears 4.5:1 on the cell under it, in every theme | The dark ramp is *reversed*, so an ink picked by ramp depth lands white-on-pale | `test_every_heatmap_value_is_legible_on_the_cell_under_it` |
| 7 | Every ramp step's ink is readable on its own cell | A dataset that does not span the ramp leaves high steps unchecked — found only by mutating step 4 | `test_every_step_of_the_ramp_is_readable_on_its_own_cell` |
| 8 | Every ramp step has an ink token | A step with none falls back to unset `fill` and renders black | `test_every_step_of_the_ramp_has_an_ink_defined_for_it` |
| 9 | Cleaning is idempotent; the counters account for every row | Re-cleaning cleaned data must change nothing, and no row may vanish unaccounted | `test_clean.py` (per-stage) |
| 10 | The page never scrolls sideways, at 400px or 1280px | A grid track floors at its items' min-content width; a `nowrap` cell widens the column and the page with it | `test_layout.py::test_the_page_does_not_scroll_sideways_*` |
| 11 | Chart type stays legible when scaled to a phone | An 11px axis number scaled to a 400px card renders at 4.8px — a smudge, not a number | `test_every_chart_stays_legible_on_a_phone` |
| 12 | The rendered page makes no network request | The offline guarantee is the reason the charts are hand-built | `test_report_pages_the_generated_csv_without_network_references` |
| 13 | The headline figure is the number of rows that survived cleaning | The obvious bug is printing the raw row count | `test_report_carries_the_cleaned_row_count_into_the_page` |
| 14 | A template is reachable without the installed package | `uv_build` package data is not guaranteed to ship | `test_the_page_shell_is_reachable_without_the_installed_package` |
| 15 | Every text token clears 4.5:1 on every surface the design declares | The README asserted it and nothing checked it, and it was false: the delivered design's muted grey is 4.16:1 on its own stone band | `test_every_text_token_is_readable_on_every_surface_the_design_declares` |
| 16 | The accent, where it is used as text, is readable where it lands | A lime accent is 1.70:1 on white; used as link text on the page ground it is invisible, and the page looks fine | `test_where_the_accent_is_used_as_text_it_can_be_read` |
| 17 | `color-scheme` promises exactly the themes the page can paint | `light dark` on a light-only page hands the reader dark scrollbars and dark form controls | `test_the_shell_promises_exactly_the_themes_the_page_can_paint` |

Invariants 1–11 and 15–16 are checked against **both** templates — the live design and the
design starter — so a design swap cannot drop out of the contract. That is deliberate:
the starter is only worth handing over if it is complete, and a second, parallel set of
checks for it would drift out of step with the first.

---

## 6 · Extension points

### Add a channel

1. `schema.py` — add it to `CHANNELS`, add its short form to `CHANNEL_SHORT`, add every
   spelling an export might use to `CHANNEL_SYNONYMS`.
2. The template — add a `--ch-8` token in every theme scope the design declares.
3. Nothing else. The charts iterate the schema, so bars, stacks, the heatmap, all four
   tables and every count pick it up.

Seven is the categorical limit this design was validated for (the dataviz rule is ≤8
slots, never cycled). An eighth channel means an eighth slot in every scope, and the
palette checks that come with it.

### Add an analysis

1. `metrics.py` — a pure function over `Sequence[Interaction]`, returning a dataclass.
2. `charts.py` — a function from that dataclass to an SVG string, naming tokens.
3. `report.py` — build the slots: a takeaway, the chart, **and the table twin**.
4. The template — the markup that renders them, plus the slot names.

The table twin is not optional. Every value a chart encodes must also exist as text, so
nothing lives only inside a hover.

### Swap the design

Copy `templates/design-template.html`, restyle it, and render it:

```python
report.document(slots, report.load_template("my-design.html"))
```

Then run the suite. `tests/test_template_slots.py` reads `TEMPLATES` — add the new
filename there and the contract checks run against it unchanged. Keep the token *names*
(`--ch-3`, `--seq-2-ink`) and change the values; those names are part of the contract
between `charts.py` and the design.

### Change the cleaning policy

`clean.py` is an ordered list of stages, each returning rows plus a counter. The counters
are not a log — they are the **data basis panel**, rendered on the page. So a new rule is
not finished until it is counted:

1. Add the stage to `_STAGE_LABELS` (the label is user-visible prose).
2. Add the stage in order — order matters, and the tests pin it.
3. Idempotence: re-cleaning cleaned data must change nothing.
4. `test_clean.py` — a test with a row that trips the rule and a row that must not.

---

## 7 · Decisions and why

| Decision | Rationale |
|---|---|
| **Hand-built SVG, no chart library** | The offline guarantee is a feature, not an accident. It also means the chart's ink is checked against the template's CSS, which no library would allow. |
| **The header mark is drawn inline, not loaded** | The same guarantee: a mark referenced by URL — even the delivered design's own asset path — is a hole on a machine with no network, and the report is read from a USB stick as often as from a server. |
| **Tokens, never literal colours, in the charts** | It is the mechanism of the design handoff. It also makes the palette *computable* from the template's own text — invariant 6 is a computed WCAG ratio, not a review comment. |
| **The template is a fragment** (no `<!doctype>`, `<html>`, `<head>`, `<body>`) | It is the form the artifact host expects and the form a designer hands over. The page shell is boilerplate, so `report.document()` adds it. |
| **Statics live in the template; the view model emits strings, never markup** | The split is what makes the design a template edit. The three exceptions — takeaways, table twins, the shell — are prose *about this dataset* or boilerplate, and are documented as such in `report.py`. |
| **A missing slot raises** | Failing loudly at build time beats a page that quietly lost its headline number. |
| **Nothing is imputed** | A missing engagement score keeps its row in the volume and is excluded from every average. An implausible duration is set to nothing, not trimmed to a plausible lie. The data basis panel says so on the page. |
| **`03/04/2026` reads as 3 April, documented** | Guessing per file would make the tool's output depend on an unstated assumption. An export that means 4 March is converted before it reaches the tool. |
| **A theme is declared, not implied** | `design-template.html` carries all three theme states; `report.html` commits to light, as the delivered design does. Committing to one is allowed — but the page still paints its ground and every colour explicitly, and `color-scheme` follows the rendered page rather than a constant, so the promise and the paint cannot drift apart. |
| **The hero chart sits on a card, not on the green panel** | A chart is drawn on the surface its palette was validated against. On the panel it would paint `--text-secondary` labels and a `--seq-6` line — both dark on dark. |
| **The browser tests skip, they do not fail, without Chrome** | A missing browser is a gap in the development machine, not a defect in the page. |

---

## 8 · What is deliberately absent

- **No filtering, drill-down or cross-chart selection.** A snapshot, not a dashboard.
- **No persistence or server.** No database, no config file, no state between runs.
- **No i18n layer.** One document, one language: the report's visible text is German and
  the CLI is English, both fixed in the source as literal strings and label tables. There
  is no locale negotiation and no message catalogue, because a report whose text depends
  on where it was generated is not reproducible. Channel synonyms accept German spellings
  on input, which is a data concern rather than a UI one.
- **No plugin or chart registry.** Four charts, each a function. A registry would be
  ceremony over a list.
- **No format guessing.** Ambiguous dates follow one documented convention rather than a
  heuristic.

---

## 9 · Known limits

The README carries the reader-facing ones, with the reasoning: the channel palette
failing three of the validator's checks and why that is permitted, the seven-step
approximation of a continuous range and its two palest steps, the phone chart floor and
its scroll trade-off, the hero card, the header mark that is drawn inline rather than
loaded, the corporate typefaces that cannot come across, and the `03/04/2026` convention.
