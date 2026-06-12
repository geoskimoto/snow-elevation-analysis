from datetime import datetime

import plotly.graph_objects as go
import pandas as pd

_PALETTE = [
    '#0072B2', '#E69F00', '#56B4E9', '#009E73',
    '#F0E442', '#D55E00', '#CC79A7', '#000000',
    '#999999', '#117733', '#882255', '#AA4499',
]


def make_huc2_figure(df: pd.DataFrame, date: datetime) -> go.Figure:
    date_label = date.strftime('%B %d, %Y')
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
        yaxis_title='Elevation (m)',
        template='plotly_white',
    )
    return fig


def make_huc4_figure(bands_by_subbasin: dict, date: datetime) -> go.Figure:
    date_label = date.strftime('%B %d, %Y')
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
        yaxis_title='Elevation (m)',
        template='plotly_white',
        legend={'font': {'size': 8}},
    )
    return fig
