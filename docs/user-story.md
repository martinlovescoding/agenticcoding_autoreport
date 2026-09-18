# User Story — Multichannel Engagement Report

## Persona

**Dr. Elena Vasquez**, Commercial Insights Lead at a mid-size pharma company. She owns
the monthly field-force review. Her data lives in an export from the CRM: one row per
HCP interaction, pulled by hand from three different systems that disagree about
spelling, date format, and what to do with a blank cell.

## Story

> **As** a Commercial Insights Lead preparing the monthly field-force review,
> **I want** a single command that turns the raw CRM export into a self-contained,
> shareable HTML report,
> **so that** I can spend the review discussing what the data means instead of
> spending two days cleaning it in a spreadsheet and rebuilding the same charts.

## Why this, why now

The report is rebuilt from scratch every month. The work is not analysis — it is
transcription: re-normalizing the same seven channel names, re-deciding whether a
negative call duration means "12 minutes" or "drop the row", re-deriving the same
monthly totals. The analysis itself takes an hour; the spreadsheet takes two days.

The task is therefore not "make a chart". It is **make the cleaning decisions once,
in code, and show them**. A report that silently drops 16 of 200 rows is worse than no
report, because the reader cannot tell whether the drop was a bug or a policy.

## Acceptance criteria

### AC1 — One command, one file

- **Given** a raw CRM export CSV,
- **When** I run `uv run python -m agenticcoding report --input data/raw_activities.csv --out report.html`,
- **Then** `report.html` is written and opens correctly with no network connection.

*Rationale: the report gets emailed to people behind a corporate proxy. A report that
loads a chart library from a CDN is a report that shows blank rectangles in the
meeting.*

### AC2 — The cleaning is visible, not silent

- **Given** an export containing duplicate interaction ids, unparseable dates, future
  dates, negative durations, out-of-range scores and blank labels,
- **Then** the report shows a **Data basis** panel naming every repair stage and how
  many rows it touched, plus the raw → analysable row count.

*Rationale: `200 raw rows → 184 analysable (92 %)` is a sentence Elena can defend in
the meeting. "The numbers looked wrong so I filtered some rows out" is not.*

### AC3 — Repairs over drops

- **Given** a row whose only defect is a repairable value (score `140`, duration `-12`,
  blank product),
- **Then** the row survives: the score is clamped to `100`, the duration read as `12`,
  the product labelled `Unknown`.
- **And** a row is dropped **only** when it cannot be attributed at all — no id, an
  unrecognized channel, or a missing/invalid/future date.

*Rationale: discarding real volume over a transcription slip understates the business.
Erasing the evidence of the slip overstates the data quality. Repair, and count it.*

### AC4 — Three analyses, each with a chart and a table

- **Given** cleaned rows,
- **Then** the report contains:
  1. **Channel mix** — volume, HCP reach and mean engagement per channel, ranked.
  2. **Monthly trend** — interactions per month, split by channel.
  3. **Specialty matrix** — mean engagement per specialty × channel, as a heatmap.
- **And** every chart has a table twin, so no value is reachable only by hovering.

*Rationale: a number that exists only inside a tooltip cannot be quoted, printed, or
read by a screen reader.*

### AC5 — Missing values are excluded, never invented

- **Given** a row with no engagement score,
- **Then** it counts toward volume and HCP reach,
- **And** it is excluded from every average.

*Rationale: imputing a mean would make the report look tidier and be wrong. The number
of scored rows is itself a finding.*

### AC6 — One palette, validated, in every theme the page declares

- **Given** the seven canonical channels,
- **Then** each has a fixed colour that is identical in every chart, and the palette
  passes the colour-vision-deficiency and contrast checks in every theme the page
  paints — which for the shipped report is one, and for the starter design is three.

*Rationale: colour must follow the entity, not its rank — a channel must not change
colour because it moved from rank 3 to rank 4 between months. And the checks have to
be *computed*: a theme the page declares but never validates is a theme somebody
reads and cannot read.*

### AC7 — The design is a drop-in

- **Given** a design delivered later as HTML/CSS/JS,
- **When** it is merged into `templates/report.html`,
- **Then** the pipeline, metrics and tests are untouched, and a slot-parity test fails
  loudly if a slot was renamed or lost.

*Rationale: the design is expected to change; the analysis is not.*

## Out of scope

- No live data connection, no database, no server — the report is a static snapshot.
- No filter UI: a filter that changes the series count must not repaint the survivors,
  and a snapshot avoids that class of bug entirely.
- No imputation of missing values.
- No competitor benchmarking or territory ranking in this iteration (considered and
  deferred — see the plan's history).

## Definition of done

1. `uv run pytest -q` is green.
2. `report.html` renders from a freshly generated 200-row CSV and is correct in every
   theme it declares, at phone width, and by keyboard alone.
3. The palette has been validated by script, not by eye, in every declared theme.
4. The report has been opened and looked at — the validator checks colour, not layout.
5. Everything is pushed to the repository.
