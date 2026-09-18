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

The page is in **German**; the command line stays English, because the report is the
product and the CLI is the tool. A masthead (period, source file, generated date), a hero
carrying the monthly total as a line and the four headline figures, then three analyses —
each with a takeaway sentence, a chart, and a table twin — and a **data basis** panel that
accounts for every row the pipeline dropped:

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
--bg  --card  --stone  --stone-light    /* the page, a card, the stone band */
--text-primary  --text-secondary  --text-muted
--grid  --axis  --accent  --tip-bg  --tip-fg
--green  --green-deep  --panel-fg  --panel-muted   /* the dark green ground */
--ch-1 … --ch-7          /* the seven channels, in schema order */
--seq-1 … --seq-7        /* magnitude, one hue light→dark, plus a -ink per step */
```

Colour follows the **entity, not the rank**: `ch-4` is Rep Email wherever it ranks. Text
never wears a series colour — a label's fill is only ever an `-ink` token, chosen for
readability on the surface behind it.

**Every text token clears 4.5:1 on every surface it can land on**, and it is *computed*:
`test_every_text_token_is_readable_on_every_surface_the_design_declares` reads the tokens
out of the template's own CSS and multiplies them. That check is why `--text-muted` is
`#616161` rather than the delivered design's `#6b6b6b` — the design's muted grey reaches
only 4.16:1 on its own stone band. The token moved; the band stayed where the design put
it. The dark green panel carries its own ink for the same reason: white on it is 14.16:1,
and the page's `--text-primary` on it is 1.2:1.

**Two theme states, deliberately.** The report is light-only, as the delivered design is.
A committed single-theme design may skip the dark blocks — but it must still paint its
ground and every colour explicitly, which this one does, and it must not *promise* a theme
it cannot paint. So `report.document` reads the rendered page back and sets `color-scheme`
from what it finds: a page with no dark scope says `light`, not `light dark`, because the
latter hands the reader a dark scrollbar and dark form controls over a light page. The
rule is tested across both templates, so the starter — which *is* theme-aware — keeps its
three states and the report keeps its one.

The `.panel` rule re-points the text tokens at the panel's own ink, so every header, hero
and footer element is readable by default rather than only if its author remembered.

**Safety net.** `tests/test_template_slots.py` compares the slots in the template against
the keys `report.py` supplies, in both directions, and re-derives the palette from the
template's own CSS to check every heatmap value against the cell under it. A renamed slot
or an unreadable ink fails a test instead of rendering a hole.

**Starting a new design.** `templates/design-template.html` is a complete, restyleable
starter — every slot, every palette token, all three theme scopes — and the suite holds it
to *the same* contract as the live design, so it cannot rot. It carries one design
deliberately: the canonical three-state theme pattern, which the live design does not use
and which a new design is likely to want. Render it with the real data to see what it
looks like:

```python
report.document(slots, report.load_template("design-template.html"))
```

`docs/architecture.md` has the shape of the system and which decisions are load-bearing;
`AGENTS.md` has the rules for changing it.

## Tests

```bash
uv run pytest
```

368 tests. Beyond the pipeline and the charts, five of them open the rendered page in a
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

- **The channel palette is the brand's, not the validator's, and it fails three of its
  checks.** `#08312a` and `#b6cdbf` sit outside the lightness band; `#08312a`, `#6b8375`
  and `#b6cdbf` fall under the chroma floor — they read as grey; and `#00b862`, `#b6cdbf`
  and `#e0a100` are below 3:1 against the surface. The CVD and normal-vision separation
  checks *pass*, so no two neighbours are confusable. This is a documented deviation rather
  than an oversight: a contrast warning obliges relief, and the relief is present and
  computed — every bar carries its value as text, every chart has a table twin, and the
  legend swatches carry the names. Under the validator's strictest setting (`--pairs all`,
  every hue against every other rather than against its neighbours) the set does not pass;
  the report therefore never relies on telling two distant channels apart by colour.
- The magnitude ramp is a seven-step approximation of the engagement range, not a
  continuous scale. Cells within one step are not distinguishable by shade — the
  **two palest steps are 4.5 ΔE apart**, so they separate only when they sit next to each
  other. The delivered design's own ramp is eleven greens; this one omits `#4a8466`, the
  single step where neither white (4.39:1) nor near-black (4.48:1) reaches 4.5:1 — the
  design sets white text there. `test_every_step_of_the_ramp_is_readable_on_its_own_cell`
  fails the delivered ramp as-is.
- The palest ramp step is 1.15:1 against the card it sits on. It reads as a cell only in
  the company of the darker steps; a heatmap whose lowest value is *also* its only value
  would be a nearly blank cell.
- **On a phone the charts scroll inside their own card.** Scaled to a 400px screen the
  charts' 11px axis numbers rendered at 4.8px, so below 640px a chart keeps a 620px floor
  and its card scrolls instead — legible type, but the longest bar's value label sits off
  the right edge until you scroll. The page body itself never scrolls sideways, and the
  table twin under each chart has every number in it without any scrolling at all.
- **A chart is always drawn on the surface its palette was validated against.** The hero
  chart sits in a white card lifted over the green panel rather than on the panel itself:
  drawn on the green ground it would paint its labels in `--text-secondary` and its line in
  `--seq-6`, and both are dark on dark.
- **The delivered design's wordmark and logo are replaced by a neutral title block.** A
  generated report should not present itself as a document issued by a company it has no
  relationship with.
- `03/04/2026` is read as 3 April. The convention is documented here rather than inferred
  per file; an export that means 4 March must be converted before it reaches this tool.
- The page is a snapshot. Filters, drill-down and cross-chart selection are out of scope.
