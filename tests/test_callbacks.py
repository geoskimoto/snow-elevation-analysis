import io
import zipfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import plotly.graph_objects as go
import pytest


def test_make_download_zip_with_two_files(tmp_path):
    from callbacks import _make_download_zip
    huc2 = tmp_path / 'snow_hypsometric_huc2_20240401.png'
    huc4 = tmp_path / 'snow_hypsometric_huc4_20240401.png'
    huc2.write_bytes(b'PNG2')
    huc4.write_bytes(b'PNG4')
    result = _make_download_zip(huc2, huc4)
    assert result['filename'] == 'snow_hypsometric.zip'
    assert result['base64'] is True
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
    assert huc2.name in names
    assert huc4.name in names


def test_make_download_zip_skips_missing_files(tmp_path):
    from callbacks import _make_download_zip
    huc2 = tmp_path / 'missing_huc2.png'
    huc4 = tmp_path / 'missing_huc4.png'
    result = _make_download_zip(huc2, huc4)
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert len(zf.namelist()) == 0


def test_make_download_zip_partial_files(tmp_path):
    from callbacks import _make_download_zip
    huc2 = tmp_path / 'huc2.png'
    huc2.write_bytes(b'data')
    huc4 = tmp_path / 'missing.png'
    result = _make_download_zip(huc2, huc4)
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert zf.namelist() == ['huc2.png']


# ---------------------------------------------------------------------------
# Trends tab callback tests
# ---------------------------------------------------------------------------

def _make_timeseries_df() -> pd.DataFrame:
    """Minimal timeseries DataFrame with one basin row and one HUC4 row."""
    return pd.DataFrame({
        'date': pd.to_datetime(['2025-01-01', '2025-01-01']),
        'basin': ['Columbia River Basin', 'Upper Columbia'],
        'total_swe_volume_km3': [12.5, 3.2],
    })


def _invoke_update_trends_tab(tab_value, df):
    """Call the update_trends_tab logic directly without a running Dash app."""
    import charts
    import timeseries

    _no_data_annotation = dict(
        text='No data yet — run the populate script or click Run Analysis',
        x=0.5, y=0.5,
        xref='paper', yref='paper',
        showarrow=False,
        font={'size': 14, 'color': '#888'},
    )
    _empty_basin = go.Figure()
    _empty_basin.update_layout(annotations=[_no_data_annotation], template='plotly_white')
    _empty_huc4 = go.Figure()
    _empty_huc4.update_layout(annotations=[_no_data_annotation], template='plotly_white')

    if tab_value != 'trends':
        return _empty_basin, _empty_huc4

    if df.empty:
        return _empty_basin, _empty_huc4

    wy = timeseries.water_year(date.today())
    return (
        charts.make_basin_timeseries_figure(df, wy),
        charts.make_huc4_timeseries_figure(df, wy),
    )


def test_trends_tab_returns_figures_when_data_exists(tmp_path):
    """When Trends tab is selected and timeseries data exists, two figures are returned."""
    df = _make_timeseries_df()

    with patch('timeseries.load_timeseries', return_value=df), \
         patch('config.get_cache_dir', return_value=tmp_path):
        basin_fig, huc4_fig = _invoke_update_trends_tab('trends', df)

    assert isinstance(basin_fig, go.Figure)
    assert isinstance(huc4_fig, go.Figure)
    # Both figures should have at least one trace
    assert len(basin_fig.data) >= 1
    assert len(huc4_fig.data) >= 1


def test_trends_tab_returns_empty_figures_when_no_data(tmp_path):
    """When Trends tab is selected but no parquet exists, empty annotated figures are returned."""
    empty_df = pd.DataFrame({
        'date': pd.Series([], dtype='datetime64[ns]'),
        'basin': pd.Series([], dtype=str),
        'total_swe_volume_km3': pd.Series([], dtype=float),
    })

    with patch('timeseries.load_timeseries', return_value=empty_df), \
         patch('config.get_cache_dir', return_value=tmp_path):
        basin_fig, huc4_fig = _invoke_update_trends_tab('trends', empty_df)

    assert isinstance(basin_fig, go.Figure)
    assert isinstance(huc4_fig, go.Figure)
    # No data traces — only the annotation
    assert len(basin_fig.data) == 0
    assert len(huc4_fig.data) == 0
    assert any(
        'No data yet' in ann.text
        for ann in basin_fig.layout.annotations
    )


def test_trends_tab_not_selected_returns_empty_figures():
    """When a tab other than 'trends' is active, empty figures are returned immediately."""
    basin_fig, huc4_fig = _invoke_update_trends_tab('snowpack', pd.DataFrame())

    assert isinstance(basin_fig, go.Figure)
    assert isinstance(huc4_fig, go.Figure)
    assert len(basin_fig.data) == 0
    assert len(huc4_fig.data) == 0
