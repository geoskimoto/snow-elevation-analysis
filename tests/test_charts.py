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


def test_make_huc2_figure_has_one_trace(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    assert len(fig.data) == 1


def test_make_huc2_figure_x_is_swe(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    assert list(fig.data[0].x) == [5.0, 80.0, 200.0, 180.0]


def test_make_huc2_figure_y_is_elevation(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    assert list(fig.data[0].y) == [0, 250, 500, 750]


def test_make_huc2_figure_xaxis_label(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    assert 'mm' in fig.layout.xaxis.title.text


def test_make_huc2_figure_yaxis_label(sample_df):
    from charts import make_huc2_figure
    fig = make_huc2_figure(sample_df, datetime(2024, 4, 1))
    assert 'm' in fig.layout.yaxis.title.text


def test_make_huc4_figure_returns_figure(sample_huc4):
    from charts import make_huc4_figure
    fig = make_huc4_figure(sample_huc4, datetime(2024, 4, 1))
    assert isinstance(fig, go.Figure)


def test_make_huc4_figure_has_trace_per_basin(sample_huc4):
    from charts import make_huc4_figure
    fig = make_huc4_figure(sample_huc4, datetime(2024, 4, 1))
    assert len(fig.data) == 2


def test_make_huc4_figure_uses_different_colors(sample_huc4):
    from charts import make_huc4_figure
    fig = make_huc4_figure(sample_huc4, datetime(2024, 4, 1))
    colors = [trace.line.color for trace in fig.data]
    assert colors[0] != colors[1]


def test_make_huc4_figure_empty_dict():
    from charts import make_huc4_figure
    fig = make_huc4_figure({}, datetime(2024, 4, 1))
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


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
    assert 'km' in fig.layout.yaxis.title.text


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
    assert 'km' in fig.layout.yaxis.title.text


def test_make_huc4_timeseries_figure_uses_different_colors(timeseries_df):
    from charts import make_huc4_timeseries_figure
    fig = make_huc4_timeseries_figure(timeseries_df, 2024)
    colors = [trace.line.color for trace in fig.data]
    assert colors[0] != colors[1]
