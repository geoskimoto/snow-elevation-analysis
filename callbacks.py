import base64
import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
from dash import Output, Input, State, no_update, html

import charts
import climatology
import config
import datasets
import pipeline
import timeseries
from basin_loader import transboundary_hucs, dagger

# Computed once at import: display-layer transboundary flags (see spec
# 2026-07-23-swann-reenable-huc6-design.md — daggers never enter parquets).
_TB = transboundary_hucs()


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


def build_historical_view(df, wy: int, huc: str | None,
                          dataset: str = 'snodas') -> tuple[go.Figure, str]:
    """Return ``(figure, caption)`` for the Historical tab.

    Pure function of an already-loaded all-water-years DataFrame — no I/O — so
    it is unit-testable and shared by the Dash callback. Degrades to an
    annotated empty figure when there is no data or too little history.
    """
    huc = huc or '17'
    ds = datasets.get(dataset)
    label = dagger(climatology.display_name(df, huc) or huc, huc, _TB)
    if df.empty:
        if dataset == 'snodas':
            msg = 'No data yet — run populate_timeseries.py to build the record.'
        else:
            msg = (f'{ds["label"]} data not yet loaded — run '
                   f'populate_timeseries.py --dataset {dataset} to backfill.')
        return _annotated_empty_figure(msg), ''

    n_years = climatology.n_historical_years(df, huc, wy)
    if n_years < climatology.MIN_YEARS_FOR_ENVELOPE:
        return _annotated_empty_figure(
            f'Not enough {ds["label"]} history for {label} yet — {n_years} prior '
            f'water year(s); need at least {climatology.MIN_YEARS_FOR_ENVELOPE}. '
            f'Run the full-record backfill to populate.'), ''

    clim = climatology.compute_climatology(df, huc, wy)
    current = climatology.current_series(df, huc, wy)
    summary = climatology.summarize_current(df, huc, wy)
    hist_wys = sorted(df[(df['huc'] == huc) & (df['wy'] != wy)]['wy'].unique())
    record_label = f'WY{hist_wys[0]}–WY{hist_wys[-1]} envelope ({n_years} years)'
    basin_label = f'{label} ({huc})' if len(huc) > 2 else label
    fig = charts.make_climatology_figure(
        clim, current, basin_label, wy, summary,
        dataset_label=ds['label'], record_label=record_label)
    caption = (f'{ds["label"]} envelope from {n_years} water years '
               f'(WY{hist_wys[0]}–WY{hist_wys[-1]}) for {basin_label}; '
               f'bold line is WY{wy}.')
    return fig, caption


def huc6_children(df, huc4: str):
    """Rows for the HUC6 children of a HUC4 (huc startswith + length 6)."""
    return df[(df['huc'].str.startswith(huc4)) & (df['huc'].str.len() == 6)]


def display_frame(df, tb):
    """Copy of a volume frame with transboundary display names daggered."""
    out = df.copy()
    out['basin'] = [dagger(n, h, tb) for n, h in zip(out['basin'], out['huc'])]
    return out


def drill_group_label(names: dict, huc4: str) -> str:
    """Drill-down chart title prefix, always carrying the HUC4 code.

    WBD names collide across levels (1704 'Upper Snake' has a child 170402
    also named 'Upper Snake'), so a name-only title reads as if basins are
    missing from the chart.
    """
    parent = names.get(huc4)
    return f'{parent} ({huc4}) HUC6 Basins' if parent else f'{huc4} HUC6 Basins'


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
        Output('date-picker', 'min_date_allowed'),
        Input('dataset-select', 'value'),
    )
    def update_date_bounds(dataset):
        return datasets.get(dataset)['start'].date().isoformat()

    @app.callback(
        Output('snowpack-footnote', 'children'),
        Input('dataset-select', 'value'),
    )
    def update_snowpack_footnote(dataset):
        ds = datasets.get(dataset)
        return [html.P([html.Strong('Data: '), ds['footnote']],
                       style={'margin': '0'})]

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
        state=[
            State('date-picker', 'date'),
            State('dataset-select', 'value'),
        ],
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
    def run_analysis(set_progress, n_clicks, date_str, dataset):
        _empty = (
            go.Figure(), go.Figure(), go.Figure(), go.Figure(),
            {'display': 'none'}, '', {},
        )
        if not date_str:
            return _empty[:4] + ({'display': 'none'}, 'Please select a date.', {})
        result = pipeline.run_pipeline(date_str, set_progress, dataset=dataset)
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
                'huc6_bands': result['huc6_bands'],
                'names': result['names'],
                'date_str': date_str,
                'dataset': dataset,
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
        dataset = store_data.get('dataset', 'snodas')
        ds = datasets.get(dataset)
        wy = timeseries.water_year(date.today())
        df = timeseries.load_timeseries(wy, config.get_cache_dir(), dataset=dataset)
        named_figs = [
            (f'swe_by_elevation_basin_{date_str}.png',   go.Figure(store_data['huc2_fig'])),
            (f'swe_by_elevation_huc4_{date_str}.png',    go.Figure(store_data['huc4_fig'])),
            (f'swe_volume_basin_{date_str}.png',         go.Figure(store_data['huc2_vol_fig'])),
            (f'swe_volume_huc4_{date_str}.png',          go.Figure(store_data['huc4_vol_fig'])),
            (f'swe_trend_basin_WY{wy}.png',              charts.make_basin_timeseries_figure(
                df[df['huc'] == '17'], wy, dataset_label=ds['label'])),
            (f'swe_trend_huc4_WY{wy}.png',               charts.make_huc4_timeseries_figure(
                df[df['huc'].str.len() == 4], wy, dataset_label=ds['label'])),
        ]
        result = _figs_to_zip(named_figs)
        result['filename'] = f'snow_analysis_{dataset}.zip'
        return result

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
        dataset = store_data.get('dataset', 'snodas')
        ds = datasets.get(dataset)
        wy = timeseries.water_year(date.today())
        df = timeseries.load_timeseries(wy, config.get_cache_dir(), dataset=dataset)
        figs = [
            ('Columbia Basin — SWE by Elevation', go.Figure(store_data['huc2_fig'])),
            ('HUC4 Subbasins — SWE by Elevation', go.Figure(store_data['huc4_fig'])),
            ('Columbia Basin — SWE Volume by Elevation', go.Figure(store_data['huc2_vol_fig'])),
            ('HUC4 Subbasins — SWE Volume by Elevation', go.Figure(store_data['huc4_vol_fig'])),
            ('Columbia Basin — SWE Volume Trend', charts.make_basin_timeseries_figure(
                df[df['huc'] == '17'], wy, dataset_label=ds['label'])),
            ('HUC4 Subbasins — SWE Volume Trend', charts.make_huc4_timeseries_figure(
                df[df['huc'].str.len() == 4], wy, dataset_label=ds['label'])),
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
    <strong>Data:</strong> {ds['footnote']}
  </p>
</body>
</html>"""
        return {
            'content': html_content,
            'filename': f'snow_analysis_{dataset}_{date_str}.html',
            'base64': False,
            'type': 'text/html',
        }

    @app.callback(
        Output('basin-timeseries-graph', 'figure'),
        Output('huc4-timeseries-graph', 'figure'),
        Input('main-tabs', 'value'),
        Input('dataset-select', 'value'),
    )
    def update_trends_tab(tab_value, dataset):
        ds = datasets.get(dataset)
        _no_data_annotation = dict(
            text=(f'No {ds["label"]} data yet — run the populate script'
                  + ('' if dataset == 'snodas' else f' with --dataset {dataset}')
                  + ' or click Run Analysis'),
            x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
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
        df = timeseries.load_timeseries(wy, cache_dir, dataset=dataset)

        if df.empty:
            return _empty_basin, _empty_huc4

        return (
            charts.make_basin_timeseries_figure(
                display_frame(df[df['huc'] == '17'], _TB), wy,
                dataset_label=ds['label']),
            charts.make_huc4_timeseries_figure(
                display_frame(df[df['huc'].str.len() == 4], _TB), wy,
                dataset_label=ds['label']),
        )

    @app.callback(
        Output('historical-basin', 'options'),
        Input('main-tabs', 'value'),
        Input('dataset-select', 'value'),
    )
    def populate_historical_basins(tab_value, dataset):
        if tab_value != 'historical':
            return no_update
        df = climatology.load_all_water_years(config.get_cache_dir(), dataset=dataset)
        if df.empty:
            return no_update
        hucs = (df[['huc', 'basin']].drop_duplicates()
                .sort_values('huc').itertuples())
        options = []
        for r in hucs:
            name = dagger(r.basin, r.huc, _TB)
            label = (name if r.huc == '17' else f'{r.huc} — {name}')
            options.append({'label': label, 'value': r.huc})
        return options

    @app.callback(
        Output('climatology-graph', 'figure'),
        Output('historical-summary', 'children'),
        Input('main-tabs', 'value'),
        Input('historical-basin', 'value'),
        Input('dataset-select', 'value'),
    )
    def update_historical_tab(tab_value, huc, dataset):
        if tab_value != 'historical':
            return _annotated_empty_figure(''), ''
        # Read-only: climatology serves committed volume parquets. It never
        # fetches SNODAS or writes cache, so it behaves identically on the
        # scheduled server and on Posit Connect (which cannot run jobs).
        df = climatology.load_all_water_years(config.get_cache_dir(), dataset=dataset)
        wy = timeseries.water_year(date.today())
        return build_historical_view(df, wy, huc, dataset=dataset)

    @app.callback(
        Output('huc6-graph', 'figure'),
        Output('huc6-volume-graph', 'figure'),
        Input('result-store', 'data'),
        Input('snowpack-drill', 'value'),
    )
    def update_snowpack_drilldown(store_data, huc4):
        if not store_data or 'huc6_bands' not in store_data or not huc4:
            return _annotated_empty_figure('Run an analysis to populate the drill-down.'), \
                   _annotated_empty_figure('')
        import pandas as pd
        names = store_data.get('names', {})
        children = {
            dagger(names.get(h, h), h, _TB): pd.DataFrame(rows)
            for h, rows in store_data['huc6_bands'].items()
            if h.startswith(huc4)
        }
        if not children:
            return _annotated_empty_figure('No HUC6 children for this subregion.'), \
                   _annotated_empty_figure('')
        date_ = datetime.strptime(store_data['date_str'], '%Y-%m-%d')
        ds = datasets.get(store_data.get('dataset', 'snodas'))
        label = drill_group_label(
            {huc4: dagger(names.get(huc4, huc4), huc4, _TB)}, huc4)
        return (charts.make_huc4_figure(children, date_, dataset_label=ds['label'],
                                        group_label=label),
                charts.make_huc4_volume_figure(children, date_, dataset_label=ds['label'],
                                               group_label=label))

    @app.callback(
        Output('huc6-timeseries-graph', 'figure'),
        Input('main-tabs', 'value'),
        Input('trends-drill', 'value'),
        Input('dataset-select', 'value'),
    )
    def update_trends_drilldown(tab_value, huc4, dataset):
        if tab_value != 'trends' or not huc4:
            return _annotated_empty_figure('')
        wy = timeseries.water_year(date.today())
        df = timeseries.load_timeseries(wy, config.get_cache_dir(), dataset=dataset)
        children = huc6_children(df, huc4)
        if children.empty:
            return _annotated_empty_figure('No data yet for this subregion.')
        ds = datasets.get(dataset)
        names = {h: dagger(n, h, _TB)
                 for h, n in zip(df['huc'], df['basin'])}
        return charts.make_huc4_timeseries_figure(
            display_frame(children, _TB), wy, dataset_label=ds['label'],
            group_label=drill_group_label(names, huc4))
