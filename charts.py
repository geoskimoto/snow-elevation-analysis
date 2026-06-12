from datetime import datetime

import plotly.graph_objects as go
import pandas as pd

_PALETTE = [
    '#0072B2', '#E69F00', '#56B4E9', '#009E73',
    '#F0E442', '#D55E00', '#CC79A7', '#000000',
    '#999999', '#117733', '#882255', '#AA4499',
]

_M_TO_FT = 3.28084
_MM_TO_IN = 0.0393701
_KM3_TO_MAF = 0.810713

# Tight margins that work on both desktop and mobile
_MARGIN_SINGLE = dict(l=55, r=55, t=70, b=50)
_MARGIN_MULTI  = dict(l=55, r=55, t=70, b=140)

_LEGEND_BELOW = dict(
    orientation='h',
    yanchor='top', y=-0.15,
    xanchor='center', x=0.5,
    font={'size': 8},
    tracegroupgap=4,
)


def _m_axis(y_range_ft: list) -> dict:
    """Return yaxis2 config that mirrors a feet axis in meters."""
    return dict(
        title='Elevation (m)',
        overlaying='y',
        side='right',
        range=[y / _M_TO_FT for y in y_range_ft],
        showgrid=False,
    )


def _y_range_ft(dfs: list) -> list:
    """Compute [min, max] elevation in feet across one or more DataFrames."""
    non_empty = [df['elev_band_m'] for df in dfs if not df.empty]
    if not non_empty:
        return [0, 4000 * _M_TO_FT]
    all_vals = pd.concat(non_empty)
    return [float(all_vals.min()) * _M_TO_FT, float(all_vals.max()) * _M_TO_FT]


def make_huc2_figure(df: pd.DataFrame, date: datetime) -> go.Figure:
    date_label = date.strftime('%b %d, %Y')
    yr = _y_range_ft([df])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['mean_swe_mm'] * _MM_TO_IN,
        y=df['elev_band_m'] * _M_TO_FT,
        mode='lines',
        line={'color': _PALETTE[0], 'width': 2},
        name='Columbia River Basin',
    ))
    fig.add_trace(go.Scatter(x=[None], y=[None], yaxis='y2', showlegend=False))
    fig.update_layout(
        title=dict(text=f'Columbia Basin — SWE by Elevation<br>{date_label}', font={'size': 13}),
        xaxis_title='Mean SWE (in)',
        yaxis=dict(title='Elevation (ft)', range=yr),
        yaxis2=_m_axis(yr),
        template='plotly_white',
        showlegend=False,
        margin=_MARGIN_SINGLE,
    )
    return fig


def make_huc4_figure(bands_by_subbasin: dict, date: datetime) -> go.Figure:
    date_label = date.strftime('%b %d, %Y')
    yr = _y_range_ft(list(bands_by_subbasin.values()))
    fig = go.Figure()
    for i, (name, df) in enumerate(sorted(bands_by_subbasin.items())):
        fig.add_trace(go.Scatter(
            x=df['mean_swe_mm'] * _MM_TO_IN,
            y=df['elev_band_m'] * _M_TO_FT,
            mode='lines',
            line={'color': _PALETTE[i % len(_PALETTE)], 'width': 1.5},
            name=name,
        ))
    fig.add_trace(go.Scatter(x=[None], y=[None], yaxis='y2', showlegend=False))
    fig.update_layout(
        title=dict(text=f'HUC4 Subbasins — SWE by Elevation<br>{date_label}', font={'size': 13}),
        xaxis_title='Mean SWE (in)',
        yaxis=dict(title='Elevation (ft)', range=yr),
        yaxis2=_m_axis(yr),
        template='plotly_white',
        legend=_LEGEND_BELOW,
        margin=_MARGIN_MULTI,
    )
    return fig


def make_huc2_volume_figure(df: pd.DataFrame, date: datetime) -> go.Figure:
    date_label = date.strftime('%b %d, %Y')
    yr = _y_range_ft([df])
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['total_swe_volume_km3'] * _KM3_TO_MAF,
        y=df['elev_band_m'] * _M_TO_FT,
        orientation='h',
        marker_color=_PALETTE[0],
        name='Columbia River Basin',
    ))
    fig.add_trace(go.Bar(x=[None], y=[None], yaxis='y2', showlegend=False))
    fig.update_layout(
        title=dict(text=f'Columbia Basin — Volume by Elevation<br>{date_label}', font={'size': 13}),
        xaxis_title='SWE Volume (MAF)',
        yaxis=dict(title='Elevation (ft)', range=yr),
        yaxis2=_m_axis(yr),
        template='plotly_white',
        showlegend=False,
        margin=_MARGIN_SINGLE,
    )
    return fig


def make_huc4_volume_figure(bands_by_subbasin: dict, date: datetime) -> go.Figure:
    date_label = date.strftime('%b %d, %Y')
    yr = _y_range_ft(list(bands_by_subbasin.values()))
    fig = go.Figure()
    for i, (name, df) in enumerate(sorted(bands_by_subbasin.items())):
        fig.add_trace(go.Bar(
            x=df['total_swe_volume_km3'] * _KM3_TO_MAF,
            y=df['elev_band_m'] * _M_TO_FT,
            orientation='h',
            marker_color=_PALETTE[i % len(_PALETTE)],
            name=name,
            opacity=0.85,
        ))
    fig.add_trace(go.Bar(x=[None], y=[None], yaxis='y2', showlegend=False))
    fig.update_layout(
        title=dict(text=f'HUC4 Subbasins — Volume by Elevation<br>{date_label}', font={'size': 13}),
        xaxis_title='SWE Volume (MAF)',
        yaxis=dict(title='Elevation (ft)', range=yr),
        yaxis2=_m_axis(yr),
        template='plotly_white',
        legend=_LEGEND_BELOW,
        margin=_MARGIN_MULTI,
        barmode='stack',
    )
    return fig


def make_basin_timeseries_figure(df: pd.DataFrame, wy: int) -> go.Figure:
    basin_df = df[df['basin'] == 'Columbia River Basin']
    if basin_df.empty:
        return go.Figure()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=basin_df['date'],
        y=basin_df['total_swe_volume_km3'] * _KM3_TO_MAF,
        mode='lines',
        line={'color': _PALETTE[0], 'width': 2},
        name='Columbia River Basin',
    ))
    fig.update_layout(
        title=dict(text=f'Columbia Basin — SWE Volume WY{wy}', font={'size': 13}),
        xaxis_title='Date',
        yaxis_title='SWE Volume (MAF)',
        template='plotly_white',
        showlegend=False,
        margin=_MARGIN_SINGLE,
    )
    return fig


def make_huc4_timeseries_figure(df: pd.DataFrame, wy: int) -> go.Figure:
    if df.empty:
        return go.Figure()
    subbasin_df = df[df['basin'] != 'Columbia River Basin']
    fig = go.Figure()
    for i, name in enumerate(sorted(subbasin_df['basin'].unique())):
        trace_df = subbasin_df[subbasin_df['basin'] == name]
        fig.add_trace(go.Scatter(
            x=trace_df['date'],
            y=trace_df['total_swe_volume_km3'] * _KM3_TO_MAF,
            mode='lines',
            line={'color': _PALETTE[i % len(_PALETTE)], 'width': 1.5},
            name=name,
        ))
    fig.update_layout(
        title=dict(text=f'HUC4 Subbasins — SWE Volume WY{wy}', font={'size': 13}),
        xaxis_title='Date',
        yaxis_title='SWE Volume (MAF)',
        template='plotly_white',
        legend=_LEGEND_BELOW,
        margin=_MARGIN_MULTI,
    )
    return fig
