"""The three analyses and the KPI block.

Every expected number here is hand-computed from `conftest.SAMPLE` — see the
comment block above that fixture for the arithmetic.
"""

import pytest

from agenticcoding import metrics

# --- channel mix --------------------------------------------------------------


def test_channel_mix_counts_interactions_per_channel(sample):
    mix = metrics.channel_mix(sample)

    by_channel = {row.channel: row for row in mix.rows}
    assert by_channel["F2F Call"].interactions == 3
    assert by_channel["Rep Email"].interactions == 3
    assert by_channel["Web"].interactions == 2


def test_channel_mix_averages_only_the_scored_rows(sample):
    mix = metrics.channel_mix(sample)

    by_channel = {row.channel: row for row in mix.rows}
    assert by_channel["F2F Call"].avg_engagement == pytest.approx(70.0)
    assert by_channel["Rep Email"].avg_engagement == pytest.approx(30.0)
    assert by_channel["Web"].avg_engagement == pytest.approx(50.0), "I8 has no score"


def test_channel_mix_counts_distinct_hcps(sample):
    mix = metrics.channel_mix(sample)

    by_channel = {row.channel: row for row in mix.rows}
    assert by_channel["F2F Call"].hcps == 2
    assert by_channel["Web"].hcps == 1


def test_channel_mix_shares_are_percent_of_all_interactions(sample):
    mix = metrics.channel_mix(sample)

    by_channel = {row.channel: row for row in mix.rows}
    assert by_channel["F2F Call"].share == pytest.approx(37.5)
    assert by_channel["Web"].share == pytest.approx(25.0)
    assert sum(row.share for row in mix.rows) == pytest.approx(100.0)


def test_channel_mix_is_ranked_by_volume(sample):
    mix = metrics.channel_mix(sample)

    assert [row.channel for row in mix.rows] == ["F2F Call", "Rep Email", "Web"]


def test_channel_mix_breaks_ties_by_report_order(sample):
    """F2F and Rep Email both have 3; F2F comes first in `schema.CHANNELS`."""
    mix = metrics.channel_mix(sample)

    assert [row.interactions for row in mix.rows] == [3, 3, 2]


def test_channel_mix_omits_channels_with_no_interactions(sample):
    mix = metrics.channel_mix(sample)

    assert "Event" not in {row.channel for row in mix.rows}
    assert len(mix.rows) == 3


def test_channel_mix_total_is_every_row(sample):
    assert metrics.channel_mix(sample).total == 8


def test_channel_mix_on_empty_input():
    mix = metrics.channel_mix([])

    assert mix.rows == ()
    assert mix.total == 0


# --- monthly trend ------------------------------------------------------------


def test_monthly_trend_covers_every_month_present(sample):
    trend = metrics.monthly_trend(sample)

    assert [month.month for month in trend.months] == ["2026-03", "2026-04", "2026-05"]


def test_monthly_trend_labels_are_three_letter_months(sample):
    trend = metrics.monthly_trend(sample)

    assert [month.label for month in trend.months] == ["Mar", "Apr", "May"]


def test_monthly_trend_splits_each_month_by_channel(sample):
    trend = metrics.monthly_trend(sample)
    by_month = {month.month: month for month in trend.months}

    assert by_month["2026-03"].counts == {"F2F Call": 2, "Rep Email": 1}
    assert by_month["2026-04"].counts == {"F2F Call": 1, "Rep Email": 2}
    assert by_month["2026-05"].counts == {"Web": 2}


def test_monthly_trend_month_totals(sample):
    trend = metrics.monthly_trend(sample)

    assert [month.total for month in trend.months] == [3, 3, 2]
    assert trend.max_total == 3


def test_monthly_trend_lists_channels_in_report_order(sample):
    trend = metrics.monthly_trend(sample)

    assert trend.channels == ("F2F Call", "Rep Email", "Web")


def test_monthly_trend_on_empty_input():
    trend = metrics.monthly_trend([])

    assert trend.months == ()
    assert trend.channels == ()
    assert trend.max_total == 0


# --- specialty matrix ---------------------------------------------------------


def test_specialty_matrix_averages_per_specialty_and_channel(sample):
    matrix = metrics.specialty_matrix(sample)
    by_specialty = {row.specialty: row for row in matrix.rows}

    assert by_specialty["Oncology"].cells["F2F Call"] == pytest.approx(70.0)
    assert by_specialty["Oncology"].cells["Rep Email"] == pytest.approx(40.0)
    assert by_specialty["Oncology"].cells["Web"] == pytest.approx(50.0)
    assert by_specialty["Cardiology"].cells["Rep Email"] == pytest.approx(25.0)


def test_specialty_matrix_marks_absent_combinations_as_none(sample):
    matrix = metrics.specialty_matrix(sample)
    by_specialty = {row.specialty: row for row in matrix.rows}

    assert by_specialty["Cardiology"].cells["Web"] is None


def test_specialty_matrix_rows_and_columns_follow_schema_order(sample):
    matrix = metrics.specialty_matrix(sample)

    assert [row.specialty for row in matrix.rows] == ["Oncology", "Cardiology"]
    assert matrix.channels == ("F2F Call", "Rep Email", "Web")


def test_specialty_matrix_reports_the_value_range_for_the_colour_scale(sample):
    matrix = metrics.specialty_matrix(sample)

    assert matrix.min_value == pytest.approx(25.0)
    assert matrix.max_value == pytest.approx(70.0)


def test_specialty_matrix_on_empty_input():
    matrix = metrics.specialty_matrix([])

    assert matrix.rows == ()
    assert matrix.channels == ()
    assert matrix.min_value == 0.0
    assert matrix.max_value == 0.0


# --- kpis ---------------------------------------------------------------------


def test_kpi_interaction_and_hcp_counts(sample):
    kpi = metrics.kpis(sample)

    assert kpi.interactions == 8
    assert kpi.hcps == 4


def test_kpi_average_engagement_ignores_missing_scores(sample):
    kpi = metrics.kpis(sample)

    assert kpi.avg_engagement == pytest.approx(50.0), "350 over 7 scored rows"


def test_kpi_email_open_rate_is_opens_over_emails(sample):
    kpi = metrics.kpis(sample)

    assert kpi.email_open_rate == pytest.approx(200.0 / 3)


def test_kpi_click_rate_is_clicks_over_opens(sample):
    kpi = metrics.kpis(sample)

    assert kpi.email_click_rate == pytest.approx(50.0)


def test_kpi_on_empty_input_returns_none_rates():
    kpi = metrics.kpis([])

    assert kpi.interactions == 0
    assert kpi.hcps == 0
    assert kpi.avg_engagement is None
    assert kpi.email_open_rate is None
    assert kpi.email_click_rate is None


# --- robustness ---------------------------------------------------------------


def test_a_group_whose_scores_are_all_missing_yields_none():
    rows = [
        metrics_row("I1", "F2F Call", None),
        metrics_row("I2", "F2F Call", None),
    ]

    mix = metrics.channel_mix(rows)

    assert mix.rows[0].avg_engagement is None


def test_rows_without_an_hcp_id_do_not_create_a_phantom_hcp():
    rows = [
        metrics_row("I1", "F2F Call", 50.0, hcp_id=""),
        metrics_row("I2", "F2F Call", 60.0, hcp_id=""),
        metrics_row("I3", "F2F Call", 70.0, hcp_id="H9"),
    ]

    mix = metrics.channel_mix(rows)

    assert mix.rows[0].hcps == 1


def metrics_row(
    interaction_id: str,
    channel: str,
    score: float | None,
    *,
    hcp_id: str = "H1",
    day: int = 1,
    month: int = 3,
):
    """A minimal cleaned row for the robustness cases."""
    import datetime as dt

    from agenticcoding import schema

    return schema.Interaction(
        interaction_id=interaction_id,
        date=dt.date(2026, month, day),
        rep_name="Alice",
        hcp_id=hcp_id,
        specialty="Oncology",
        channel=channel,
        product="Zorvex",
        duration_min=10,
        engagement_score=score,
        opened=None,
        clicked=None,
    )
