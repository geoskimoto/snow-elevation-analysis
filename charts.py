from datetime import datetime

import plotly.graph_objects as go
import pandas as pd

_PALETTE = [
    '#0072B2', '#E69F00', '#56B4E9', '#009E73',
    '#F0E442', '#D55E00', '#CC79A7', '#000000',
    '#999999', '#117733', '#882255', '#AA4499',
]

_M_TO_FT = 3.28084


def _ft_axis(y_range_m: list) -> dict:
    """Return yaxis2 config that mirrors a meters axis in feet."""
    return dict(
        title='Elevation (ft)',
        overlaying='y',
        side='right',
        range=[y * _M_TO_FT for y in y_range_m],
        showgrid=False,
    )


def _y_range(dfs: list) -> list:
    """Compute [min, max] elevation across one or more DataFrames."""
    non_empty = [df['elev_band_m'] for df in dfs if not df.empty]
    if not non_empty:
        return [0, 4000]
    all_vals = pd.concat(non_empty)
    return [float(all_vals.min()), float(all_vals.max())]


def make_huc2_figure(df: pd.DataFrame, date: datetime) -> go.Figure:
    date_label = date.strftime('%B %d, %Y')
    yr = _y_range([df])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['mean_swe_mm'],
        y=df['elev_band_m'],
        mode='lines',
        line={'color': _PALETTE[0], 'width': 2},
        name='Columbia River Basin',
    ))
    fig.update_layout(
        title=f'Columbia River Basin<br>SWE by Elevation — {date_label}',
        xaxis_title='Mean SWE (mm)',
        yaxis=dict(title='Elevation (m)', range=yr),
        yaxis2=_ft_axis(yr),
        template='plotly_white',
    )
    return fig


def make_huc4_figure(bands_by_subbasin: dict, date: datetime) -> go.Figure:
    date_label = date.strftime('%B %d, %Y')
    yr = _y_range(list(bands_by_subbasin.values()))
    fig = go.Figure()
    for i, (name, df) in enumerate(sorted(bands_by_subbasin.items())):
        fig.add_trace(go.Scatter(
            x=df['mean_swe_mm'],
            y=df['elev_band_m'],
            mode='lines',
            line={'color': _PALETTE[i % len(_PALETTE)], 'width': 1.5},
            name=name,
        ))
    fig.update_layout(
        title=f'Columbia River Basin — HUC4 Subbasins<br>SWE by Elevation — {date_label}',
        xaxis_title='Mean SWE (mm)',
        yaxis=dict(title='Elevation (m)', range=yr),
        yaxis2=_ft_axis(yr),
        template='plotly_white',
        legend={'font': {'size': 8}},
    )
    return fig


def make_huc2_volume_figure(df: pd.DataFrame, date: datetime) -> go.Figure:
    date_label = date.strftime('%B %d, %Y')
    yr = _y_range([df])
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['total_swe_volume_km3'],
        y=df['elev_band_m'],
        orientation='h',
        marker_color=_PALETTE[0],
        name='Columbia River Basin',
    ))
    fig.update_layout(
        title=f'Columbia River Basin<br>SWE Volume by Elevation — {date_label}',
        xaxis_title='Total SWE Volume (km³)',
        yaxis=dict(title='Elevation (m)', range=yr),
        yaxis2=_ft_axis(yr),
        template='plotly_white',
    )
    return fig


def make_huc4_volume_figure(bands_by_subbasin: dict, date: datetime) -> go.Figure:
    date_label = date.strftime('%B %d, %Y')
    yr = _y_range(list(bands_by_subbasin.values()))
    fig = go.Figure()
    for i, (name, df) in enumerate(sorted(bands_by_subbasin.items())):
        fig.add_trace(go.Bar(
            x=df['total_swe_volume_km3'],
            y=df['elev_band_m'],
            orientation='h',
            marker_color=_PALETTE[i % len(_PALETTE)],
            name=name,
        ))
    fig.update_layout(
        title=f'Columbia River Basin — HUC4 Subbasins<br>SWE Volume by Elevation — {date_label}',
        xaxis_title='Total SWE Volume (km³)',
        yaxis=dict(title='Elevation (m)', range=yr),
        yaxis2=_ft_axis(yr),
        template='plotly_white',
        legend={'font': {'size': 8}},
        barmode='group',
    )
    return fig


def make_basin_timeseries_figure(df: pd.DataFrame, wy: int) -> go.Figure:
    """Return a single-line time series of Columbia River Basin SWE volume."""
    basin_df = df[df['basin'] == 'Columbia River Basin']
    if basin_df.empty:
        return go.Figure()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=basin_df['date'],
        y=basin_df['total_swe_volume_km3'],
        mode='lines',
        line={'color': _PALETTE[0], 'width': 2},
        name='Columbia River Basin',
    ))
    fig.update_layout(
        title=f'Columbia River Basin — SWE Volume<br>Water Year {wy}',
        xaxis_title='Date',
        yaxis_title='Total SWE Volume (km³)',
        template='plotly_white',
    )
    return fig


def make_huc4_timeseries_figure(df: pd.DataFrame, wy: int) -> go.Figure:
    """Return one line per HUC4 subbasin (excludes Columbia River Basin) for SWE volume."""
    if df.empty:
        return go.Figure()
    subbasin_df = df[df['basin'] != 'Columbia River Basin']
    fig = go.Figure()
    for i, name in enumerate(sorted(subbasin_df['basin'].unique())):
        trace_df = subbasin_df[subbasin_df['basin'] == name]
        fig.add_trace(go.Scatter(
            x=trace_df['date'],
            y=trace_df['total_swe_volume_km3'],
            mode='lines',
            line={'color': _PALETTE[i % len(_PALETTE)], 'width': 1.5},
            name=name,
        ))
    fig.update_layout(
        title=f'HUC4 Subbasins — SWE Volume<br>Water Year {wy}',
        xaxis_title='Date',
        yaxis_title='Total SWE Volume (km³)',
        template='plotly_white',
        legend={'font': {'size': 8}},
    )
    return fig
