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
--surface-1  --surface-2  --text-primary  --text-secondary  --text-muted
--grid  --axis
--ch-1 … --ch-7          /* the seven channels, in schema order */
--seq-1 … --seq-5        /* magnitude, one hue light→dark, plus a -ink per step */
```

Colour follows the **entity, not the rank**: `ch-4` is Rep Email wherever it ranks. Text
never wears a series colour — a label's fill is only ever an `-ink` token, chosen for
readability on the surface behind it. Dark mode is defined twice, under both
`@media (prefers-color-scheme: dark)` and `:root[data-theme="dark"]`, so a theme toggle
wins in either direction.

**Safety net.** `tests/test_template_slots.py` compares the slots in the template against
the keys `report.py` supplies, in both directions, and re-derives the palette from the
template's own CSS to check every heatmap value against the cell under it. A renamed slot
or an unreadable ink fails a test instead of rendering a hole.

## Tests

```bash
uv run pytest
```

300 tests. Beyond the pipeline and the charts, three of them open the rendered page in a
real browser and measure it at 400px and 1280px — a page that scrolls sideways is a layout
bug no unit test can see. They skip when no Chrome or Chromium is installed.

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
- `03/04/2026` is read as 3 April. The convention is documented here rather than inferred
  per file; an export that means 4 March must be converted before it reaches this tool.
- The page is a snapshot. Filters, drill-down and cross-chart selection are out of scope.
