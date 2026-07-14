import pandas as pd
import pytest
from datetime import datetime
import plotly.graph_objects as go


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'elev_band_m': [0, 250, 500, 750],
        'mean_swe_mm': [5.0, 80.0, 200.0, 180.0],
        'area_km2': [100.0] * 4,
        'total_swe_volume_km3': [0.0005] * 4,
    })


@pytest.fixture
def sample_huc4(sample_df):
    return {
        'Upper Columbia': sample_df.copy(),
        'Snake River': sample_df.copy(),
    }


def test_make_huc2_figure_returns_figure(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    assert isinstance(fig, go.Figure)


def test_make_huc2_figure_has_data_trace_plus_meter_axis_trace(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    # one data trace + one invisible trace that activates the right-hand
    # meters axis (yaxis2)
    assert len(fig.data) == 2
    assert fig.data[1].yaxis == 'y2'
    assert fig.data[1].x == (None,)


def test_make_huc2_figure_x_is_swe_inches(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    # mean_swe_mm [5, 80, 200, 180] converted to inches
    assert list(fig.data[0].x) == pytest.approx(
        [0.19685, 3.14961, 7.87402, 7.08662], abs=1e-4
    )


def test_make_huc2_figure_y_is_elevation_feet(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    # elev_band_m [0, 250, 500, 750] converted to feet
    assert list(fig.data[0].y) == pytest.approx(
        [0.0, 820.21, 1640.42, 2460.63], abs=1e-2
    )


def test_make_huc2_figure_xaxis_label(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    assert '(in)' in fig.layout.xaxis.title.text


def test_make_huc2_figure_yaxis_labels(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    # feet on the primary (left) axis, meters mirrored on the right
    assert '(ft)' in fig.layout.yaxis.title.text
    assert '(m)' in fig.layout.yaxis2.title.text
    assert fig.layout.yaxis2.side == 'right'


def test_make_huc4_figure_returns_figure(sample_huc4):
    from charts import make_huc4_figure
    fig = make_huc4_figure(sample_huc4, datetime(2024, 4, 1))
    assert isinstance(fig, go.Figure)


def test_make_huc4_figure_has_trace_per_basin(sample_huc4):
    from charts import make_huc4_figure
    fig = make_huc4_figure(sample_huc4, datetime(2024, 4, 1))
    # one trace per subbasin + the meters-axis activation trace
    assert len(fig.data) == 3
    assert [t.name for t in fig.data[:2]] == ['Snake River', 'Upper Columbia']
    assert fig.data[2].yaxis == 'y2'


def test_make_huc4_figure_uses_different_colors(sample_huc4):
    from charts import make_huc4_figure
    fig = make_huc4_figure(sample_huc4, datetime(2024, 4, 1))
    colors = [trace.line.color for trace in fig.data]
    assert colors[0] != colors[1]


def test_make_huc4_figure_empty_dict():
    from charts import make_huc4_figure
    fig = make_huc4_figure({}, datetime(2024, 4, 1))
    assert isinstance(fig, go.Figure)
    # no basin traces — only the meters-axis activation trace remains
    assert len(fig.data) == 1
    assert fig.data[0].yaxis == 'y2'


# ---------------------------------------------------------------------------
# Timeseries fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def timeseries_df():
    dates = pd.date_range('2024-10-01', periods=4, freq='W')
    return pd.DataFrame({
        'date': list(dates) * 3,
        'basin': (
            ['Columbia River Basin'] * 4
            + ['Upper Columbia'] * 4
            + ['Snake River'] * 4
        ),
        'total_swe_volume_km3': [0.1, 0.2, 0.3, 0.4] * 3,
    })


# ---------------------------------------------------------------------------
# make_basin_timeseries_figure
# ---------------------------------------------------------------------------

def test_make_basin_timeseries_figure_returns_figure(timeseries_df):
    from charts import make_basin_timeseries_figure
    fig = make_basin_timeseries_figure(timeseries_df, 2024)
    assert isinstance(fig, go.Figure)


def test_make_basin_timeseries_figure_has_one_trace(timeseries_df):
    from charts import make_basin_timeseries_figure
    fig = make_basin_timeseries_figure(timeseries_df, 2024)
    assert len(fig.data) == 1


def test_make_basin_timeseries_figure_empty_df_returns_empty():
    from charts import make_basin_timeseries_figure
    empty = pd.DataFrame(columns=['date', 'basin', 'total_swe_volume_km3'])
    fig = make_basin_timeseries_figure(empty, 2024)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_make_basin_timeseries_figure_no_columbia_rows_returns_empty():
    from charts import make_basin_timeseries_figure
    df = pd.DataFrame({
        'date': pd.date_range('2024-10-01', periods=2, freq='W'),
        'basin': ['Snake River', 'Upper Columbia'],
        'total_swe_volume_km3': [0.1, 0.2],
    })
    fig = make_basin_timeseries_figure(df, 2024)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_make_basin_timeseries_figure_xaxis_title(timeseries_df):
    from charts import make_basin_timeseries_figure
    fig = make_basin_timeseries_figure(timeseries_df, 2024)
    assert fig.layout.xaxis.title.text == 'Date'


def test_make_basin_timeseries_figure_yaxis_title(timeseries_df):
    from charts import make_basin_timeseries_figure
    fig = make_basin_timeseries_figure(timeseries_df, 2024)
    assert 'MAF' in fig.layout.yaxis.title.text


# ---------------------------------------------------------------------------
# make_huc4_timeseries_figure
# ---------------------------------------------------------------------------

def test_make_huc4_timeseries_figure_returns_figure(timeseries_df):
    from charts import make_huc4_timeseries_figure
    fig = make_huc4_timeseries_figure(timeseries_df, 2024)
    assert isinstance(fig, go.Figure)


def test_make_huc4_timeseries_figure_trace_count(timeseries_df):
    from charts import make_huc4_timeseries_figure
    fig = make_huc4_timeseries_figure(timeseries_df, 2024)
    # timeseries_df has 2 subbasins: Upper Columbia, Snake River
    assert len(fig.data) == 2


def test_make_huc4_timeseries_figure_excludes_columbia(timeseries_df):
    from charts import make_huc4_timeseries_figure
    fig = make_huc4_timeseries_figure(timeseries_df, 2024)
    trace_names = [t.name for t in fig.data]
    assert 'Columbia River Basin' not in trace_names


def test_make_huc4_timeseries_figure_empty_df_returns_empty():
    from charts import make_huc4_timeseries_figure
    empty = pd.DataFrame(columns=['date', 'basin', 'total_swe_volume_km3'])
    fig = make_huc4_timeseries_figure(empty, 2024)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_make_huc4_timeseries_figure_xaxis_title(timeseries_df):
    from charts import make_huc4_timeseries_figure
    fig = make_huc4_timeseries_figure(timeseries_df, 2024)
    assert fig.layout.xaxis.title.text == 'Date'


def test_make_huc4_timeseries_figure_yaxis_title(timeseries_df):
    from charts import make_huc4_timeseries_figure
    fig = make_huc4_timeseries_figure(timeseries_df, 2024)
    assert 'MAF' in fig.layout.yaxis.title.text


def test_make_huc4_timeseries_figure_uses_different_colors(timeseries_df):
    from charts import make_huc4_timeseries_figure
    fig = make_huc4_timeseries_figure(timeseries_df, 2024)
    colors = [trace.line.color for trace in fig.data]
    assert colors[0] != colors[1]


# ---------------------------------------------------------------------------
# make_climatology_figure
# ---------------------------------------------------------------------------

@pytest.fixture
def clim_df():
    """A minimal 3-day percentile envelope (columns as compute_climatology)."""
    return pd.DataFrame({
        'dow': [1, 2, 3],
        'ref_date': pd.to_datetime(['2022-10-01', '2022-10-02', '2022-10-03']),
        'min': [1.0, 2.0, 3.0],
        'p10': [1.5, 2.5, 3.5],
        'p25': [2.0, 3.0, 4.0],
        'p50': [3.0, 4.0, 5.0],
        'p75': [4.0, 5.0, 6.0],
        'p90': [4.5, 5.5, 6.5],
        'max': [5.0, 6.0, 7.0],
        'n': [10, 10, 10],
    })


@pytest.fixture
def clim_current_df():
    return pd.DataFrame({
        'dow': [1, 2, 3],
        'ref_date': pd.to_datetime(['2022-10-01', '2022-10-02', '2022-10-03']),
        'date': pd.to_datetime(['2025-10-01', '2025-10-02', '2025-10-03']),
        'total_swe_volume_km3': [3.2, 4.1, 5.5],
    })


def test_make_climatology_figure_returns_figure(clim_df, clim_current_df):
    from charts import make_climatology_figure
    fig = make_climatology_figure(clim_df, clim_current_df, 'Columbia River Basin', 2026)
    assert isinstance(fig, go.Figure)


def test_make_climatology_figure_trace_count(clim_df, clim_current_df):
    from charts import make_climatology_figure
    fig = make_climatology_figure(clim_df, clim_current_df, 'Columbia River Basin', 2026)
    # 3 band pairs (6) + median (1) + current year (1)
    assert len(fig.data) == 8


def test_make_climatology_figure_without_current_year(clim_df):
    from charts import make_climatology_figure
    empty_current = pd.DataFrame(columns=['dow', 'ref_date', 'date', 'total_swe_volume_km3'])
    fig = make_climatology_figure(clim_df, empty_current, 'Columbia River Basin', 2026)
    # 3 band pairs (6) + median (1), no current-year line
    assert len(fig.data) == 7
    assert all(t.name != 'WY2026' for t in fig.data)


def test_make_climatology_figure_empty_clim_shows_annotation(clim_current_df):
    from charts import make_climatology_figure
    empty = pd.DataFrame(columns=['dow', 'ref_date', 'min', 'p10', 'p25',
                                   'p50', 'p75', 'p90', 'max', 'n'])
    fig = make_climatology_figure(empty, clim_current_df, 'Columbia River Basin', 2026)
    assert len(fig.data) == 0
    assert len(fig.layout.annotations) == 1
    assert 'history' in fig.layout.annotations[0].text.lower()


def test_make_climatology_figure_current_year_maf_and_style(clim_df, clim_current_df):
    from charts import make_climatology_figure, _CURRENT_YEAR_COLOR, _KM3_TO_MAF
    fig = make_climatology_figure(clim_df, clim_current_df, 'Columbia River Basin', 2026)
    current = next(t for t in fig.data if t.name == 'WY2026')
    assert list(current.y) == pytest.approx([v * _KM3_TO_MAF for v in [3.2, 4.1, 5.5]])
    assert current.line.color == _CURRENT_YEAR_COLOR


def test_make_climatology_figure_median_dashed(clim_df, clim_current_df):
    from charts import make_climatology_figure
    fig = make_climatology_figure(clim_df, clim_current_df, 'Columbia River Basin', 2026)
    median = next(t for t in fig.data if t.name == 'Median')
    assert median.line.dash == 'dash'


def test_make_climatology_figure_yaxis_title(clim_df, clim_current_df):
    from charts import make_climatology_figure
    fig = make_climatology_figure(clim_df, clim_current_df, 'Columbia River Basin', 2026)
    assert 'MAF' in fig.layout.yaxis.title.text


def test_make_climatology_figure_summary_in_title(clim_df, clim_current_df):
    from charts import make_climatology_figure
    summary = {
        'pct_of_median': 92.0,
        'rank_from_bottom': 5,
        'total_years': 22,
        'as_of': pd.Timestamp('2026-01-15'),
    }
    fig = make_climatology_figure(clim_df, clim_current_df, 'Columbia River Basin', 2026, summary)
    assert '92% of median' in fig.layout.title.text
    assert 'ranked 5 of 22' in fig.layout.title.text
