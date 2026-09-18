# agenticcoding — multichannel engagement report

Turns a raw CRM export of pharma field-force activity into one self-contained
`report.html`: the data cleaned and accounted for, three analyses with a chart and a
table each, readable offline in one file.

The report is a **snapshot**, not a dashboard. It is a static page with no server, no
database and no config file.

## Quickstart

```bash
uv sync

# 1 · a synthetic raw export, deliberately dirty (200 rows, fixed seed)
uv run python -m agenticcoding generate --rows 200 --out data/raw_activities.csv

# 2 · clean it and render the page
uv run python -m agenticcoding report --input data/raw_activities.csv --out report.html

# 3 · look at it
open report.html
```

`generate` is only a stand-in for a real export. `report` reads any CSV whose header
names an `interaction_id` column; anything else is refused with exit code 1 rather than
reported as "0 interactions".

## Commands

| Command | Flags |
|---|---|
| `generate` | `--rows` (200) · `--seed` (7) · `--out` |
| `report` | `--input` · `--out` · `--as-of` (today) · `--write-clean` (off) |

`--as-of` is the reference date for the "date is in the future" rule, which is what makes
a report reproducible on a later day. Cleaned rows are not written unless `--write-clean`
names a path.

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). **Runtime dependencies: none** —
everything is the standard library. The only development dependency is `pytest`. The charts
are built as inline SVG by hand.

## What the page contains

A masthead (period, source file, generated date), a KPI strip, a **data basis** panel that
accounts for every row the pipeline dropped, then three analyses — each with a takeaway
sentence, a chart, and a table twin:

| Analysis | Chart |
|---|---|
| Volume and engagement by channel | ranked horizontal bars, one colour per channel |
| How activity moved through the period | stacked columns, one segment per channel per month |
| Where engagement landed, by specialty | heatmap on a single-hue magnitude ramp |

Every value is in a table as well as in a chart, so nothing exists only inside a hover.

## Cleaning policy

Ordered, idempotent, and counted per stage — the counters are what the data basis panel
renders. Nothing is imputed: a missing engagement score keeps its row in the volume and is
excluded from every average.

| Rule | Effect |
|---|---|
| Duplicate `interaction_id` | first occurrence kept |
| Channel synonyms (`F2F`, `S2S`, `eMail`, …) | mapped to the 7 canonical channels |
| Unknown channel | row dropped — it cannot be attributed |
| Multi-format dates | unambiguous formats parsed; `03/04/2026` reads DD.MM. (documented, not guessed) |
| Future date | row dropped |
| Negative duration | absolute value |
| Implausible duration (> 300 min) | set to nothing rather than trimmed to a plausible lie |
| Engagement score outside 0–100 | clamped to the range |
| Missing product | "Unknown" |

## The design handoff

The design lives in one file: `src/agenticcoding/templates/report.html`. Python supplies
values, never markup — so swapping the design is a template edit, and the pipeline, the
metrics and the tests stay untouched.

**Slots.** Two sigils, and the difference between them is a security boundary:

- `{{NAME}}` — escaped text. Everything that came out of the CSV is untrusted input.
- `{{{NAME}}}` — raw HTML. Only markup this program rendered itself: the chart SVGs and
  the table twins.

HTML comments are neither substituted nor shipped, so the template can document its own
slot syntax. A slot the template asks for and the view model does not supply raises
`KeyError`: a report that silently loses its headline number is worse than one that
refuses to build.

**Palette.** No chart ever names a colour. Marks carry `style="fill:var(--ch-3)"`, and the
template defines the slots:

```
--bg  --card  --tile            /* the page, a chart card, a grey tile */
--band-bg  --band-fg  --band-muted
--text-primary  --text-secondary  --text-muted
--grid  --axis  --accent  --tip-bg  --tip-fg
--kpi-a … --kpi-c
--ch-1 … --ch-7          /* the seven channels, in schema order */
--seq-1 … --seq-5        /* magnitude, one hue light→dark, plus a -ink per step */
```

Colour follows the **entity, not the rank**: `ch-4` is Rep Email wherever it ranks. Text
never wears a series colour — a label's fill is only ever an `-ink` token, chosen for
readability on the surface behind it. Every text token is picked to clear 4.5:1 on every
surface it can land on, in both themes, which is why the ink is not simply inherited from
the design's palette.

Three theme states have to resolve, not two: the bare `:root` block is the complete light
palette, because an unstamped document is what most viewers see; the dark palette is
re-declared under `@media (prefers-color-scheme: dark)` guarded as
`:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`, so an
explicit choice beats the system in either direction. The inverted KPI band re-points the
text tokens at its own ink, so one set of rules styles it in both themes.

**Safety net.** `tests/test_template_slots.py` compares the slots in the template against
the keys `report.py` supplies, in both directions, and re-derives the palette from the
template's own CSS to check every heatmap value against the cell under it. A renamed slot
or an unreadable ink fails a test instead of rendering a hole.

**Starting a new design.** `templates/design-template.html` is a complete, restyleable
starter — all 24 slots, every palette token, all three theme scopes — and the suite holds
it to *the same* contract as the live design, so it cannot rot. Render it with the real
data to see what it looks like:

```python
report.document(slots, report.load_template("design-template.html"))
```

`docs/architecture.md` has the shape of the system and which decisions are load-bearing;
`AGENTS.md` has the rules for changing it.

## Tests

```bash
uv run pytest
```

328 tests. Beyond the pipeline and the charts, five of them open the rendered page in a
real browser and measure it — at 400px and at 1280px. A page that scrolls sideways, or a
chart whose type shrinks to an unreadable size when it is scaled to a phone, is a layout
bug no unit test can see: the page measures the chart's rendered width against its
viewBox and reports the smallest text the reader actually gets. They skip when no Chrome
or Chromium is installed.

The contract checks in `test_template_slots.py` run against **both** templates — the live
design and `design-template.html` — so a design swap cannot quietly drop out of the
contract, and the starter cannot rot.

## Offline guarantee

`report.html` makes no network requests. No CDN, no web font, no chart library, no
external image. The file is portable and renders the same from a USB stick with no network
at all.

## Known limitations

- **Three of the seven channel colours sit below 3:1 contrast** against the light surface
  (aqua, yellow, magenta). This is deliberate and permitted: the relief is visible — direct
  labels on every bar and a table twin under every chart, so no value is encoded by colour
  alone. Under the validator's strictest setting (`--pairs all`, every hue against every
  other rather than against its neighbours) the seven-hue set does not pass; the report
  therefore never relies on telling two distant channels apart by colour.
- The magnitude ramp is a five-step approximation of the engagement range, not a
  continuous scale. Cells within one step are not distinguishable by shade.
- **On a phone the charts scroll inside their own card.** Scaled to a 400px screen the
  charts' 11px axis numbers rendered at 4.8px, so below 640px a chart keeps a 620px floor
  and its card scrolls instead — legible type, but the longest bar's value label sits off
  the right edge until you scroll. The page body itself never scrolls sideways, and the
  table twin under each chart has every number in it without any scrolling at all.
- **A chart is always drawn on the surface its palette was validated against**, so the
  trend chart's card stays light inside the dark KPI band rather than inverting with it.
  The band is a typographic device, not a theme: inverting the chart with it would put the
  light-mode hues on a near-black ground, which is a combination no palette check covers.
- `03/04/2026` is read as 3 April. The convention is documented here rather than inferred
  per file; an export that means 4 March must be converted before it reaches this tool.
- The page is a snapshot. Filters, drill-down and cross-chart selection are out of scope.
