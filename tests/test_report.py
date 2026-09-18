"""The view model: metrics and charts in, template slots out.

`report.py` is the only place that knows both what the numbers mean and what the
template calls them. It renders no prose of its own beyond the takeaways and the
table markup — every static word lives in the template, so the design handoff never
has to touch this file.

Two rules the tests hold it to:

* **A slot is a string, never a number.** The template cannot format, so every value
  arrives already formatted by `svgcore`.
* **The table is the accessible twin of the chart.** Every value a chart encodes is
  also written out in text, so no number exists only inside a hover.
"""

import datetime as dt

import pytest

from agenticcoding import charts, clean, metrics, report, schema
from conftest import SAMPLE, interaction

# --- helpers ------------------------------------------------------------------


def quality(rows_in: int, rows_out: int, **counts: int) -> clean.QualityReport:
    """A quality report with the pipeline's real stage keys and chosen counts."""
    notes = tuple(
        clean.QualityNote(key=key, label=label, count=counts.get(key, 0))
        for key, label in clean._STAGE_LABELS
    )
    return clean.QualityReport(rows_in=rows_in, rows_out=rows_out, notes=notes)


@pytest.fixture
def slots() -> dict[str, str]:
    return report.build_slots(
        SAMPLE,
        quality(8, 8),
        source_file="data/raw_activities.csv",
        generated_at="18 September 2026",
    )


# --- the header ---------------------------------------------------------------


def test_period_label_spans_the_months_in_the_data(slots):
    """SAMPLE runs March–May 2026."""
    assert slots["PERIOD_LABEL"] == "March – May 2026"


def test_period_label_on_a_single_month_names_only_that_month():
    rows = [interaction(date=dt.date(2026, 3, 2))]
    built = report.build_slots(rows, quality(1, 1), source_file="x.csv", generated_at="now")

    assert built["PERIOD_LABEL"] == "March 2026"


def test_source_and_timestamp_are_passed_through_verbatim(slots):
    assert slots["SOURCE_FILE"] == "data/raw_activities.csv"
    assert slots["GENERATED_AT"] == "18 September 2026"


# --- the KPI strip ------------------------------------------------------------


def test_kpi_interactions_counts_every_analysable_row(slots):
    assert slots["KPI_INTERACTIONS"] == "8"


def test_kpi_hcps_counts_distinct_hcps(slots):
    """SAMPLE reaches H1–H4."""
    assert slots["KPI_HCPS"] == "4"


def test_kpi_avg_engagement_ignores_the_missing_score(slots):
    """Seven scores summing to 350 — the eighth row must not be read as a zero."""
    assert slots["KPI_AVG_ENGAGEMENT"] == "50"


def test_every_kpi_note_says_where_its_number_came_from(slots):
    """A headline figure without its denominator is a figure a reader cannot check."""
    assert slots["KPI_INTERACTIONS_NOTE"] == "from 8 raw rows"
    assert slots["KPI_HCPS_NOTE"] == "2 interactions per HCP"
    assert slots["KPI_EMAIL_OPEN_RATE_NOTE"] == "50 % of opens clicked"


def test_kpi_email_open_rate_is_a_percentage(slots):
    """Two of three emails opened."""
    assert slots["KPI_EMAIL_OPEN_RATE"] == "66.7 %"


def test_kpi_email_open_rate_on_no_email_data_is_a_dash():
    """A report with no email channel must not claim a measured 0 %."""
    rows = [interaction(channel="F2F Call")]
    built = report.build_slots(rows, quality(1, 1), source_file="x.csv", generated_at="now")

    assert built["KPI_EMAIL_OPEN_RATE"] == "—"


# --- the data-quality panel ---------------------------------------------------


def test_quality_headline_states_the_attrition(slots):
    assert slots["QUALITY_HEADLINE"] == "8 raw rows → 8 analysable (100 %)"


def test_quality_headline_rounds_the_share(slots):
    built = report.build_slots(
        SAMPLE, quality(10, 9), source_file="x.csv", generated_at="now"
    )

    assert built["QUALITY_HEADLINE"] == "10 raw rows → 9 analysable (90 %)"


def test_quality_table_has_a_row_per_stage(slots):
    table = slots["QUALITY_TABLE"]

    assert table.count("<tr") == len(clean._STAGE_LABELS) + 1, "one header row plus one per stage"
    assert "Duplicate interaction_id rows removed" in table


def test_quality_table_shows_the_count_for_each_stage():
    built = report.build_slots(
        SAMPLE, quality(8, 6, duplicates=2), source_file="x.csv", generated_at="now"
    )

    assert ">2<" in built["QUALITY_TABLE"]


def test_missing_score_note_names_how_many_rows_it_affects(slots):
    """SAMPLE has one row without a score."""
    assert slots["MISSING_SCORE_NOTE"] == (
        "Engagement score is missing on 1 of 8 interactions. Those rows count toward "
        "volume and are excluded from every average — nothing is imputed."
    )


# --- the analyses -------------------------------------------------------------


def test_hero_tagline_leads_with_the_two_numbers_the_page_is_about(slots):
    """"Cleaned and analysed" is a claim; the counts are what make it checkable."""
    tagline = slots["HERO_TAGLINE"]

    assert "8 interactions" in tagline
    assert "4 health care professionals" in tagline
    assert "March – May 2026" in tagline


def test_channel_slots_carry_a_takeaway_a_chart_and_a_table(slots):
    assert "F2F Call" in slots["CHANNEL_TAKEAWAY"]
    assert slots["CHANNEL_CHART"].startswith("<svg")
    assert slots["CHANNEL_TABLE"].startswith("<table")


def test_channel_takeaway_names_the_volume_leader(slots):
    """F2F Call tops the ranking, and also posts the highest mean engagement."""
    assert "70" in slots["CHANNEL_TAKEAWAY"]


def test_channel_takeaway_credits_the_best_engaged_channel_by_name():
    """The volume leader and the best-engaged channel are two different questions.

    Joining them with "and posts the highest average engagement" hands the volume
    leader a score that belongs to another channel — a sentence the table contradicts.
    """
    rows = [
        interaction(interaction_id=f"F{index}", channel="F2F Call", engagement_score=40.0)
        for index in range(3)
    ]
    rows.append(interaction(interaction_id="E1", channel="Event", engagement_score=90.0))
    built = report.build_slots(rows, quality(4, 4), source_file="x.csv", generated_at="now")

    sentence = built["CHANNEL_TAKEAWAY"]

    assert "<b>F2F Call</b> carries the most activity" in sentence
    assert "<b>Event</b> posts the highest average engagement" in sentence
    assert "90" in sentence


def test_channel_takeaway_does_not_repeat_the_name_it_already_gave(slots):
    """When one channel is both, naming it twice reads as two channels."""
    sentence = slots["CHANNEL_TAKEAWAY"]

    assert "<b>F2F Call</b> carries the most activity" in sentence
    assert "and posts the highest average engagement" in sentence
    assert sentence.count("F2F Call") == 1


def test_trend_slots_carry_a_legend_a_takeaway_a_chart_and_a_table(slots):
    assert slots["TREND_LEGEND"].startswith('<ul class="legend">')
    assert slots["TREND_CHART"].startswith("<svg")
    assert slots["TREND_TABLE"].startswith("<table")


def test_trend_table_has_a_row_per_month_and_a_column_per_channel(slots):
    table = slots["TREND_TABLE"]

    assert table.count("<tr") == 3 + 1, "three months plus the header"
    assert "F2F Call" in table


def test_specialty_slots_carry_a_takeaway_a_chart_and_a_table(slots):
    assert "Oncology" in slots["SPECIALTY_TAKEAWAY"]
    assert slots["SPECIALTY_CHART"].startswith("<svg")
    assert slots["SPECIALTY_TABLE"].startswith("<table")


def test_a_takeaway_emphasises_the_values_it_names(slots):
    """The design sets the sentence in grey and the number it turns on in ink.

    That emphasis is markup, so the slot is raw — and a raw slot is a promise that
    nothing inside it came from the CSV unescaped.
    """
    assert "<b>" in slots["CHANNEL_TAKEAWAY"]
    assert "<b>" in slots["SPECIALTY_TAKEAWAY"]
    assert "<b>" in slots["TREND_TAKEAWAY"]


def test_a_hostile_specialty_label_cannot_become_markup_in_a_takeaway():
    """The takeaway is substituted raw, so it escapes for itself."""
    rows = [
        interaction(specialty='<img src=x onerror="alert(1)">', engagement_score=70.0),
        interaction(interaction_id="I2", specialty="Oncology", engagement_score=30.0),
    ]
    built = report.build_slots(rows, quality(2, 2), source_file="x.csv", generated_at="now")

    assert "<img" not in built["SPECIALTY_TAKEAWAY"]
    assert "&lt;img" in built["SPECIALTY_TAKEAWAY"]


def test_specialty_table_marks_a_combination_with_no_data(slots):
    """Cardiology has no Web interaction; a blank cell would read as a zero."""
    assert "—" in slots["SPECIALTY_TABLE"]


# --- escaping and completeness ------------------------------------------------


def test_a_hostile_specialty_label_cannot_become_markup():
    """Specialties the cleaner does not recognize are kept verbatim, so they are input."""
    rows = [interaction(specialty='<img src=x onerror="alert(1)">')]
    built = report.build_slots(rows, quality(1, 1), source_file="x.csv", generated_at="now")

    assert "<img" not in built["SPECIALTY_TABLE"]
    assert "&lt;img" in built["SPECIALTY_TABLE"]


def test_the_takeaways_are_sentences_not_bare_numbers(slots):
    for name in ("CHANNEL_TAKEAWAY", "TREND_TAKEAWAY", "SPECIALTY_TAKEAWAY"):
        assert slots[name].endswith("."), name
        assert len(slots[name]) > 30, name


def test_every_slot_is_a_string(slots):
    assert all(isinstance(value, str) for value in slots.values())


def test_no_slot_leaks_an_unfilled_sigil(slots):
    assert not any("{{" in value for value in slots.values())


# --- empty input --------------------------------------------------------------


def test_an_empty_dataset_still_builds_a_report():
    """The report must render, with the charts simply absent, rather than crash."""
    built = report.build_slots([], quality(0, 0), source_file="x.csv", generated_at="now")

    assert built["KPI_INTERACTIONS"] == "0"
    assert built["KPI_AVG_ENGAGEMENT"] == "—"
    assert built["CHANNEL_CHART"] == ""
    assert built["PERIOD_LABEL"] == "No period"


# --- the document -------------------------------------------------------------


def test_document_wraps_the_fragment_in_a_standalone_page(slots):
    page = report.document(slots, report.load_template())

    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")


def test_document_hoists_the_title_out_of_the_body(slots):
    page = report.document(slots, report.load_template())

    head, _, body = page.partition("</head>")
    assert "<title>" in head
    assert "<title>" not in body


def test_document_hoists_the_stylesheet_out_of_the_body(slots):
    page = report.document(slots, report.load_template())

    head, _, body = page.partition("</head>")
    assert "<style>" in head
    assert "<style>" not in body


def test_document_declares_the_theme_for_the_os_and_for_the_toggle(slots):
    """Both scopes, or a viewer's explicit choice loses to the OS setting."""
    page = report.document(slots, report.load_template())

    assert "prefers-color-scheme: dark" in page
    assert '[data-theme="dark"]' in page


def test_document_leaves_no_unfilled_slot(slots):
    page = report.document(slots, report.load_template())

    assert "{{" not in page


def test_document_makes_no_external_requests(slots):
    """The report is read offline and shared as a file."""
    page = report.document(slots, report.load_template())

    assert "http://" not in page
    assert "https://" not in page


def test_the_charts_and_the_tables_describe_the_same_data(slots):
    """The table twin exists so no value is reachable only through a hover."""
    assert len(charts.channel_bars(metrics.channel_mix(SAMPLE))) > 0
    assert slots["CHANNEL_TABLE"].count("<tr") == len(metrics.channel_mix(SAMPLE).rows) + 1


def test_build_slots_does_not_mutate_its_input():
    rows = list(SAMPLE)
    report.build_slots(rows, quality(8, 8), source_file="x.csv", generated_at="now")

    assert rows == list(SAMPLE)
