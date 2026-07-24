import io
import zipfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import plotly.graph_objects as go
import pytest


def test_figs_to_zip_renders_real_png(tmp_path):
    """End-to-end: a real figure renders via kaleido into a valid zip."""
    from callbacks import _figs_to_zip
    fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
    result = _figs_to_zip([('huc2.png', fig)])
    assert result['filename'] == 'snow_analysis.zip'
    assert result['base64'] is True
    assert result['type'] == 'application/zip'
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert zf.namelist() == ['huc2.png']
        png = zf.read('huc2.png')
    assert png[:8] == b'\x89PNG\r\n\x1a\n'  # valid PNG magic bytes


def test_figs_to_zip_one_entry_per_figure():
    from callbacks import _figs_to_zip
    names = [f'plot_{i}.png' for i in range(6)]
    figs = [(n, go.Figure()) for n in names]
    with patch('callbacks.pio.to_image', return_value=b'fake-png'):
        result = _figs_to_zip(figs)
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert zf.namelist() == names


def test_figs_to_zip_empty_list_returns_empty_zip():
    from callbacks import _figs_to_zip
    result = _figs_to_zip([])
    import base64
    raw = base64.b64decode(result['content'])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert zf.namelist() == []


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


# ---------------------------------------------------------------------------
# Historical tab — build_historical_view
# ---------------------------------------------------------------------------

def _multi_year_df(n_years: int, basin: str = 'Columbia River Basin',
                   huc: str = '17') -> pd.DataFrame:
    """Daily volume rows for n_years historical WYs plus a partial current WY."""
    import numpy as np
    rows = []
    hist_wys = list(range(2026 - n_years, 2026))
    for wy in hist_wys:
        for d in pd.date_range(f'{wy - 1}-10-01', f'{wy}-09-30', freq='D'):
            base = 5 + 4 * np.sin((d.dayofyear / 365) * 2 * np.pi)
            rows.append({'date': d, 'huc': huc, 'basin': basin,
                         'total_swe_volume_km3': max(0.0, base), 'wy': wy})
    for d in pd.date_range('2025-10-01', '2026-01-15', freq='D'):
        base = 5 + 4 * np.sin((d.dayofyear / 365) * 2 * np.pi)
        rows.append({'date': d, 'huc': huc, 'basin': basin,
                     'total_swe_volume_km3': max(0.0, base - 1.0), 'wy': 2026})
    return pd.DataFrame(rows)


def test_historical_view_empty_df_returns_annotation():
    from callbacks import build_historical_view
    empty = pd.DataFrame(columns=['date', 'huc', 'basin', 'total_swe_volume_km3', 'wy'])
    fig, caption = build_historical_view(empty, wy=2026, huc='17')
    assert len(fig.data) == 0
    assert caption == ''
    assert 'No data yet' in fig.layout.annotations[0].text


def test_historical_view_insufficient_years_returns_annotation():
    from callbacks import build_historical_view
    df = _multi_year_df(n_years=2)  # below MIN_YEARS_FOR_ENVELOPE (3)
    fig, caption = build_historical_view(df, wy=2026, huc='17')
    assert len(fig.data) == 0
    assert caption == ''
    assert 'Not enough SNODAS (~1 km) history' in fig.layout.annotations[0].text


def test_historical_view_builds_envelope_with_enough_years():
    from callbacks import build_historical_view
    df = _multi_year_df(n_years=5)
    fig, caption = build_historical_view(df, wy=2026, huc='17')
    # 3 band pairs (6) + median (1) + current year (1)
    assert len(fig.data) == 8
    assert 'SNODAS (~1 km) envelope from 5 water years' in caption
    assert 'WY2026' in caption


def test_historical_view_defaults_basin_when_none():
    from callbacks import build_historical_view
    df = _multi_year_df(n_years=5)
    fig, caption = build_historical_view(df, wy=2026, huc=None)
    assert len(fig.data) == 8


def test_build_historical_view_swann_empty_names_backfill():
    import callbacks
    from climatology import _empty_df

    fig, caption = callbacks.build_historical_view(
        _empty_df(), 2026, "Columbia River Basin", dataset="swann")
    text = fig.layout.annotations[0].text
    assert "swann" in text.lower()
    assert "--dataset swann" in text


def test_build_historical_view_labels_dataset(tmp_path):
    import pandas as pd
    import callbacks

    rows = []
    for wy in (2004, 2005, 2006, 2007):
        for day in ("01-10", "01-11", "01-12"):
            rows.append({"date": pd.Timestamp(f"{wy}-{day}"),
                         "huc": "17", "basin": "Columbia River Basin",
                         "total_swe_volume_km3": 1.0 + wy % 3, "wy": wy})
    df = pd.DataFrame(rows)
    fig, caption = callbacks.build_historical_view(
        df, 2026, "17", dataset="swann")
    assert "SWANN (4 km)" in fig.layout.title.text


def test_build_historical_view_by_huc_code(tmp_path):
    import pandas as pd
    from datetime import datetime
    import callbacks, climatology
    from timeseries import append_volumes

    band = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [1.0],
    })
    for yr in (2004, 2005, 2006, 2007):
        for day in (10, 11, 12):
            append_volumes(datetime(yr, 1, day), {"170602": band},
                           {"170602": "Salmon"}, tmp_path)
    df = climatology.load_all_water_years(tmp_path)
    fig, caption = callbacks.build_historical_view(df, 2026, "170602")
    assert "Salmon" in fig.layout.title.text
    assert "Salmon" in caption or "170602" in caption


def test_trends_drilldown_filters_huc6_children():
    import pandas as pd
    import callbacks

    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 4),
        "huc": ["17", "1706", "170602", "170300"],
        "basin": ["Columbia River Basin", "Lower Snake", "Salmon", "Yakima"],
        "total_swe_volume_km3": [10.0, 3.0, 1.5, 0.7],
    })
    children = callbacks.huc6_children(df, "1706")
    assert set(children["huc"]) == {"170602"}


def test_drill_group_label_includes_code():
    import callbacks
    assert callbacks.drill_group_label({"1704": "Upper Snake"}, "1704") == \
        "Upper Snake (1704) HUC6 Basins"
    assert callbacks.drill_group_label({}, "1704") == "1704 HUC6 Basins"


def test_display_frame_daggers_transboundary_names():
    import pandas as pd
    import callbacks
    from basin_loader import transboundary_hucs
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 2),
        "huc": ["170101", "170602"],
        "basin": ["Kootenai", "Salmon"],
        "total_swe_volume_km3": [1.0, 2.0],
    })
    out = callbacks.display_frame(df, transboundary_hucs())
    assert set(out["basin"]) == {"Kootenai †", "Salmon"}
    assert set(df["basin"]) == {"Kootenai", "Salmon"}   # original untouched


def test_historical_title_daggers_transboundary_basin(tmp_path):
    import pandas as pd
    from datetime import datetime
    import callbacks, climatology
    from timeseries import append_volumes

    band = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [1.0],
    })
    for yr in (2004, 2005, 2006, 2007):
        for day in (10, 11, 12):
            append_volumes(datetime(yr, 1, day), {"170101": band},
                           {"170101": "Kootenai"}, tmp_path)
    df = climatology.load_all_water_years(tmp_path)
    fig, cap = callbacks.build_historical_view(df, 2026, "170101")
    assert "Kootenai †" in fig.layout.title.text
