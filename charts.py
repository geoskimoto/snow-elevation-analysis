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


_CLIMATOLOGY_BLUE = '0, 114, 178'  # rgb of _PALETTE[0], reused for band fills
_CURRENT_YEAR_COLOR = _PALETTE[5]  # '#D55E00' — contrasts with the blue envelope


def _band_trace(x, lower, upper, fill_alpha: float, name: str) -> list:
    """Return the (invisible lower bound, filled upper bound) trace pair.

    Plotly's ``fill='tonexty'`` fills between a trace and the one added just
    before it, so the lower bound must be appended immediately ahead of the
    upper bound.
    """
    fillcolor = f'rgba({_CLIMATOLOGY_BLUE}, {fill_alpha})'
    lower_trace = go.Scatter(
        x=x, y=lower, mode='lines', line={'width': 0},
        hoverinfo='skip', showlegend=False,
    )
    upper_trace = go.Scatter(
        x=x, y=upper, mode='lines', line={'width': 0},
        fill='tonexty', fillcolor=fillcolor,
        hoverinfo='skip', name=name, showlegend=True,
    )
    return [lower_trace, upper_trace]


def _climatology_empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white',
        margin=_MARGIN_SINGLE,
        annotations=[dict(
            text=message, x=0.5, y=0.5, xref='paper', yref='paper',
            showarrow=False, font={'size': 14, 'color': '#888'},
        )],
    )
    return fig


def make_climatology_figure(clim_df: pd.DataFrame, current_df: pd.DataFrame,
                            basin_label: str, wy: int, summary: dict | None = None) -> go.Figure:
    """Percentile envelope (min–max / 10–90 / 25–75 / median) with the current
    water year overlaid. Volumes are in MAF; the x-axis runs Oct → Sep.
    """
    if clim_df is None or clim_df.empty:
        return _climatology_empty_figure(
            'Not enough history yet — climatology needs several prior water years.'
        )

    x = clim_df['ref_date']
    to_maf = _KM3_TO_MAF
    fig = go.Figure()

    # Outermost band first so darker inner bands paint on top.
    fig.add_traces(_band_trace(x, clim_df['min'] * to_maf, clim_df['max'] * to_maf,
                               0.10, 'Min–Max'))
    fig.add_traces(_band_trace(x, clim_df['p10'] * to_maf, clim_df['p90'] * to_maf,
                               0.18, '10–90th pct'))
    fig.add_traces(_band_trace(x, clim_df['p25'] * to_maf, clim_df['p75'] * to_maf,
                               0.30, '25–75th pct'))

    fig.add_trace(go.Scatter(
        x=x, y=clim_df['p50'] * to_maf, mode='lines',
        line={'color': '#555555', 'width': 1.5, 'dash': 'dash'},
        name='Median',
    ))

    if current_df is not None and not current_df.empty:
        fig.add_trace(go.Scatter(
            x=current_df['ref_date'], y=current_df['total_swe_volume_km3'] * to_maf,
            mode='lines', line={'color': _CURRENT_YEAR_COLOR, 'width': 2.5},
            name=f'WY{wy}',
        ))

    title = f'{basin_label} — SWE Climatology'
    if summary:
        title += (f'<br><sub>WY{wy}: {summary["pct_of_median"]:.0f}% of median · '
                  f'ranked {summary["rank_from_bottom"]} of {summary["total_years"]} years '
                  f'(as of {summary["as_of"]:%b %d})</sub>')

    fig.update_layout(
        title=dict(text=title, font={'size': 13}),
        xaxis=dict(title='Water Year (Oct–Sep)', tickformat='%b', dtick='M1'),
        yaxis_title='SWE Volume (MAF)',
        template='plotly_white',
        legend=_LEGEND_BELOW,
        margin=dict(l=55, r=55, t=80, b=140),
        hovermode='x unified',
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
