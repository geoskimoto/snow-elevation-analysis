import base64
import io
import zipfile
from pathlib import Path

import plotly.graph_objects as go
from dash import Output, Input, State, no_update

import pipeline


def _make_download_zip(huc2_path: Path, huc4_path: Path) -> dict:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if huc2_path.exists():
            zf.write(huc2_path, huc2_path.name)
        if huc4_path.exists():
            zf.write(huc4_path, huc4_path.name)
    buf.seek(0)
    return {
        'content': base64.b64encode(buf.read()).decode(),
        'filename': 'snow_hypsometric.zip',
        'base64': True,
        'type': 'application/zip',
    }


def register(app) -> None:
    @app.callback(
        output=[
            Output('huc2-graph', 'figure'),
            Output('huc4-graph', 'figure'),
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
        if not date_str:
            return (
                go.Figure(), go.Figure(),
                {'display': 'none'}, 'Please select a date.', {},
            )
        result = pipeline.run_pipeline(date_str, set_progress)
        if result['error']:
            return (
                go.Figure(), go.Figure(),
                {'display': 'none'}, f'Error: {result["error"]}', {},
            )
        return (
            result['huc2_fig'],
            result['huc4_fig'],
            {'display': 'block'},
            '',
            {'huc2_png': result['huc2_png'], 'huc4_png': result['huc4_png']},
        )

    @app.callback(
        Output('download-data', 'data'),
        Input('download-btn', 'n_clicks'),
        State('result-store', 'data'),
        prevent_initial_call=True,
    )
    def download_pngs(n_clicks, store_data):
        if not store_data:
            return no_update
        huc2_path = Path(store_data.get('huc2_png', ''))
        huc4_path = Path(store_data.get('huc4_png', ''))
        return _make_download_zip(huc2_path, huc4_path)
