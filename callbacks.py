import base64
import io
import zipfile
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
from dash import Output, Input, State, no_update

import charts
import climatology
import config
import pipeline
import timeseries


def _annotated_empty_figure(message: str) -> go.Figure:
    """A blank plotly_white figure carrying a centered grey annotation."""
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white',
        annotations=[dict(
            text=message, x=0.5, y=0.5, xref='paper', yref='paper',
            showarrow=False, font={'size': 14, 'color': '#888'},
        )],
    )
    return fig


def build_historical_view(df, wy: int, basin: str | None) -> tuple[go.Figure, str]:
    """Return ``(figure, caption)`` for the Historical tab.

    Pure function of an already-loaded all-water-years DataFrame — no I/O — so
    it is unit-testable and shared by the Dash callback. Degrades to an
    annotated empty figure when there is no data or too little history.
    """
    basin = basin or 'Columbia River Basin'
    if df.empty:
        return _annotated_empty_figure(
            'No data yet — run populate_timeseries.py to build the record.'), ''

    n_years = climatology.n_historical_years(df, basin, wy)
    if n_years < climatology.MIN_YEARS_FOR_ENVELOPE:
        return _annotated_empty_figure(
            f'Not enough history for {basin} yet — {n_years} prior water '
            f'year(s); need at least {climatology.MIN_YEARS_FOR_ENVELOPE}. '
            f'Run the full-record backfill to populate.'), ''

    clim = climatology.compute_climatology(df, basin, wy)
    current = climatology.current_series(df, basin, wy)
    summary = climatology.summarize_current(df, basin, wy)
    fig = charts.make_climatology_figure(clim, current, basin, wy, summary)

    hist_wys = sorted(df[(df['basin'] == basin) & (df['wy'] != wy)]['wy'].unique())
    caption = (f'Envelope from {n_years} water years '
               f'(WY{hist_wys[0]}–WY{hist_wys[-1]}); bold line is WY{wy}.')
    return fig, caption


def _figs_to_zip(named_figs: list[tuple[str, go.Figure]]) -> dict:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, fig in named_figs:
            zf.writestr(filename, pio.to_image(fig, format='png', scale=2))
    buf.seek(0)
    return {
        'content': base64.b64encode(buf.read()).decode(),
        'filename': 'snow_analysis.zip',
        'base64': True,
        'type': 'application/zip',
    }


def register(app) -> None:
    @app.callback(
        output=[
            Output('huc2-graph', 'figure'),
            Output('huc4-graph', 'figure'),
            Output('huc2-volume-graph', 'figure'),
            Output('huc4-volume-graph', 'figure'),
            Output('download-section', 'style'),
            Output('error-msg', 'children'),
            Output('result-store', 'data'),
        ],
        inputs=Input('run-btn', 'n_clicks'),
        state=State('date-picker', 'date'),
        running=[
            (Output('run-btn', 'disabled'), True, False),
            (Output('progress-container', 'style'),
             {'display': 'block'}, {'display': 'none'}),
        ],
        progress=[
            Output('progress-bar', 'value'),
            Output('progress-label', 'children'),
        ],
        background=True,
        prevent_initial_call=True,
    )
    def run_analysis(set_progress, n_clicks, date_str):
        _empty = (
            go.Figure(), go.Figure(), go.Figure(), go.Figure(),
            {'display': 'none'}, '', {},
        )
        if not date_str:
            return _empty[:4] + ({'display': 'none'}, 'Please select a date.', {})
        result = pipeline.run_pipeline(date_str, set_progress)
        if result['error']:
            return _empty[:4] + ({'display': 'none'}, f'Error: {result["error"]}', {})
        return (
            result['huc2_fig'],
            result['huc4_fig'],
            result['huc2_vol_fig'],
            result['huc4_vol_fig'],
            {'display': 'block'},
            '',
            {
                'huc2_png': result['huc2_png'],
                'huc4_png': result['huc4_png'],
                'huc2_fig': result['huc2_fig'].to_dict(),
                'huc4_fig': result['huc4_fig'].to_dict(),
                'huc2_vol_fig': result['huc2_vol_fig'].to_dict(),
                'huc4_vol_fig': result['huc4_vol_fig'].to_dict(),
                'date_str': date_str,
            },
        )

    @app.callback(
        Output('download-data', 'data'),
        Input('download-btn', 'n_clicks'),
        State('result-store', 'data'),
        prevent_initial_call=True,
    )
    def download_pngs(n_clicks, store_data):
        if not store_data or 'huc2_fig' not in store_data:
            return no_update
        date_str = store_data.get('date_str', 'unknown')
        wy = timeseries.water_year(date.today())
        df = timeseries.load_timeseries(wy, config.get_cache_dir())
        named_figs = [
            (f'swe_by_elevation_basin_{date_str}.png',   go.Figure(store_data['huc2_fig'])),
            (f'swe_by_elevation_huc4_{date_str}.png',    go.Figure(store_data['huc4_fig'])),
            (f'swe_volume_basin_{date_str}.png',         go.Figure(store_data['huc2_vol_fig'])),
            (f'swe_volume_huc4_{date_str}.png',          go.Figure(store_data['huc4_vol_fig'])),
            (f'swe_trend_basin_WY{wy}.png',              charts.make_basin_timeseries_figure(df, wy)),
            (f'swe_trend_huc4_WY{wy}.png',               charts.make_huc4_timeseries_figure(df, wy)),
        ]
        return _figs_to_zip(named_figs)

    @app.callback(
        Output('download-html', 'data'),
        Input('download-html-btn', 'n_clicks'),
        State('result-store', 'data'),
        prevent_initial_call=True,
    )
    def download_html(n_clicks, store_data):
        if not store_data or 'huc2_fig' not in store_data:
            return no_update
        date_str = store_data.get('date_str', 'unknown')
        wy = timeseries.water_year(date.today())
        df = timeseries.load_timeseries(wy, config.get_cache_dir())
        figs = [
            ('Columbia Basin — SWE by Elevation', go.Figure(store_data['huc2_fig'])),
            ('HUC4 Subbasins — SWE by Elevation', go.Figure(store_data['huc4_fig'])),
            ('Columbia Basin — SWE Volume by Elevation', go.Figure(store_data['huc2_vol_fig'])),
            ('HUC4 Subbasins — SWE Volume by Elevation', go.Figure(store_data['huc4_vol_fig'])),
            ('Columbia Basin — SWE Volume Trend', charts.make_basin_timeseries_figure(df, wy)),
            ('HUC4 Subbasins — SWE Volume Trend', charts.make_huc4_timeseries_figure(df, wy)),
        ]
        plot_divs = ''.join(
            f'<div class="plot">{pio.to_html(fig, full_html=False, include_plotlyjs=False)}</div>'
            for _, fig in figs
        )
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Snow Elevation Analysis — {date_str}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ font-family: sans-serif; background: #f5f5f5; margin: 0; padding: 1rem; }}
    h1 {{ font-size: 1.2rem; color: #333; margin-bottom: 0.25rem; }}
    p.sub {{ font-size: 0.85rem; color: #666; margin: 0 0 1rem 0; }}
    .plot {{ background: white; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);
             margin-bottom: 1.5rem; padding: 0.5rem; }}
    .footnote {{ font-size: 0.75rem; color: #666; border-top: 1px solid #ddd;
                 padding-top: 0.6rem; line-height: 1.5; }}
  </style>
</head>
<body>
  <h1>Snow Elevation Analysis</h1>
  <p class="sub">Analysis date: {date_str}</p>
  {plot_divs}
  <p class="footnote">
    <strong>Data:</strong> NOAA SNODAS (~1 km daily gridded SWE). Assimilates SNOTEL/COOP ground stations
    with meteorological model forcing. <strong>Limitations:</strong> Station network thins above ~7,000 ft,
    leading to underestimation of deep mountain snowpack (published bias: 20–40% low in high-elevation basins).
    Glacier pixels are excluded. SWE drop-off above ~6,500 ft likely reflects both true late-season ablation
    on exposed terrain and SNODAS model skill degradation.
  </p>
</body>
</html>"""
        return {
            'content': html_content,
            'filename': f'snow_analysis_{date_str}.html',
            'base64': False,
            'type': 'text/html',
        }

    @app.callback(
        Output('basin-timeseries-graph', 'figure'),
        Output('huc4-timeseries-graph', 'figure'),
        Input('main-tabs', 'value'),
    )
    def update_trends_tab(tab_value):
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

        wy = timeseries.water_year(date.today())
        cache_dir = config.get_cache_dir()
        df = timeseries.load_timeseries(wy, cache_dir)

        if df.empty:
            return _empty_basin, _empty_huc4

        return (
            charts.make_basin_timeseries_figure(df, wy),
            charts.make_huc4_timeseries_figure(df, wy),
        )

    @app.callback(
        Output('historical-basin', 'options'),
        Input('main-tabs', 'value'),
    )
    def populate_historical_basins(tab_value):
        if tab_value != 'historical':
            return no_update
        df = climatology.load_all_water_years(config.get_cache_dir())
        if df.empty:
            return no_update
        basins = list(df['basin'].unique())
        huc2 = 'Columbia River Basin'
        ordered = ([huc2] if huc2 in basins else []) + sorted(b for b in basins if b != huc2)
        return [{'label': b, 'value': b} for b in ordered]

    @app.callback(
        Output('climatology-graph', 'figure'),
        Output('historical-summary', 'children'),
        Input('main-tabs', 'value'),
        Input('historical-basin', 'value'),
    )
    def update_historical_tab(tab_value, basin):
        if tab_value != 'historical':
            return _annotated_empty_figure(''), ''
        # Read-only: climatology serves committed volume parquets. It never
        # fetches SNODAS or writes cache, so it behaves identically on the
        # scheduled server and on Posit Connect (which cannot run jobs).
        df = climatology.load_all_water_years(config.get_cache_dir())
        wy = timeseries.water_year(date.today())
        return build_historical_view(df, wy, basin)
