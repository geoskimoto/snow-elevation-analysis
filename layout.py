from datetime import date

from dash import dcc, html

import datasets


def _huc4_drill_options() -> list:
    from basin_loader import load_huc4, transboundary_hucs, dagger
    g = load_huc4()
    tb = transboundary_hucs()
    return [{'label': f"{r.huc4} — {dagger(r.name, r.huc4, tb)}", 'value': r.huc4}
            for r in sorted(g.itertuples(), key=lambda r: r.huc4)]


# Section cards — same visual language as the HTML download page's .plot cards.
_CARD_STYLE = {
    'background': 'white', 'borderRadius': '6px',
    'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
    'padding': '1rem', 'marginBottom': '1.25rem',
}
_CARD_TITLE_STYLE = {'margin': '0', 'fontSize': '0.95rem', 'color': '#333'}


def _drill_card_header(title: str, dropdown_id: str) -> html.Div:
    """Card header row: section title left, that tab's drill dropdown right."""
    return html.Div([
        html.H3(title, style=_CARD_TITLE_STYLE),
        dcc.Dropdown(
            id=dropdown_id,
            options=_huc4_drill_options(),
            value='1706',
            clearable=False,
            style={'width': '300px', 'fontSize': '0.85rem'},
        ),
    ], style={'display': 'flex', 'justifyContent': 'space-between',
              'alignItems': 'center', 'marginBottom': '0.75rem'})


def get_layout() -> html.Div:
    today = date.today().isoformat()
    return html.Div([
        dcc.Store(id='result-store'),
        dcc.Download(id='download-data'),
        dcc.Download(id='download-html'),

        # Header bar
        html.Div([
            html.H2('Snow Elevation Analysis',
                    style={'margin': '0', 'color': '#333', 'fontSize': '1.2rem'}),
            dcc.RadioItems(
                id='dataset-select',
                options=[
                    # SWANN re-enabled 2026-07-23 at 35-basin granularity
                    # (dormant 2026-07-22 → 23 during the HUC6 redesign).
                    {'label': datasets.get('snodas')['label'], 'value': 'snodas'},
                    {'label': datasets.get('swann')['label'], 'value': 'swann'},
                ],
                value='snodas',
                inline=True,
                style={'fontSize': '0.85rem', 'color': '#333'},
                inputStyle={'marginRight': '0.3rem', 'marginLeft': '0.9rem'},
            ),
        ], style={
            'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center',
            'padding': '0.8rem 1.5rem', 'background': 'white',
            'boxShadow': '0 1px 4px rgba(0,0,0,0.1)', 'flexShrink': '0',
        }),

        # Body row
        html.Div([
            # Left sidebar
            html.Div([
                html.Label('Date', style={'fontWeight': 'bold', 'marginBottom': '0.3rem',
                                          'display': 'block', 'fontSize': '0.9rem'}),
                dcc.DatePickerSingle(
                    id='date-picker',
                    date=today,
                    min_date_allowed=datasets.get('snodas')['start'].date().isoformat(),
                    max_date_allowed=today,
                    display_format='YYYY-MM-DD',
                    style={'marginBottom': '1rem'},
                ),
                html.Button(
                    'Run Analysis', id='run-btn', n_clicks=0,
                    style={
                        'display': 'block', 'width': '100%', 'padding': '0.6rem',
                        'background': '#0072B2', 'color': 'white', 'border': 'none',
                        'borderRadius': '4px', 'cursor': 'pointer', 'fontSize': '0.95rem',
                        'marginBottom': '1rem',
                    },
                ),
                html.Div([
                    html.Div(id='progress-label',
                             style={'fontSize': '0.8rem', 'color': '#555',
                                    'marginBottom': '0.25rem'}),
                    dcc.Slider(
                        id='progress-bar', min=0, max=100, value=0,
                        marks=None, tooltip={'always_visible': False}, disabled=True,
                    ),
                ], id='progress-container', style={'display': 'none', 'marginBottom': '1rem'}),

                html.Div(id='error-msg',
                         style={'color': '#D55E00', 'fontSize': '0.85rem',
                                'marginBottom': '1rem'}),

                html.Div([
                    html.Button(
                        'Download PNGs', id='download-btn', n_clicks=0,
                        style={
                            'display': 'block', 'width': '100%', 'padding': '0.5rem',
                            'background': '#009E73', 'color': 'white', 'border': 'none',
                            'borderRadius': '4px', 'cursor': 'pointer', 'fontSize': '0.9rem',
                            'marginBottom': '0.5rem',
                        },
                    ),
                    html.Button(
                        'Download HTML', id='download-html-btn', n_clicks=0,
                        style={
                            'display': 'block', 'width': '100%', 'padding': '0.5rem',
                            'background': '#56B4E9', 'color': 'white', 'border': 'none',
                            'borderRadius': '4px', 'cursor': 'pointer', 'fontSize': '0.9rem',
                        },
                    ),
                ], id='download-section', style={'display': 'none'}),
            ], className='sidebar', style={
                'width': '230px', 'padding': '1.2rem', 'background': 'white',
                'boxShadow': '1px 0 4px rgba(0,0,0,0.06)', 'flexShrink': '0',
                'overflowY': 'auto',
            }),

            # Chart area — tabbed
            html.Div([
                dcc.Tabs(id='main-tabs', value='snowpack', children=[
                    dcc.Tab(label='Snowpack', value='snowpack', children=[
                        html.Div([
                            html.Div([
                                html.H3('Basin & Subregions (HUC2 · HUC4)',
                                        style={**_CARD_TITLE_STYLE,
                                               'marginBottom': '0.75rem'}),
                                html.Div([
                                    dcc.Graph(id='huc2-graph', style={'flex': '1', 'minWidth': '0'},
                                              responsive=True, config={'displayModeBar': False}),
                                    dcc.Graph(id='huc4-graph', style={'flex': '1', 'minWidth': '0'},
                                              responsive=True, config={'displayModeBar': False}),
                                ], className='chart-pair',
                                   style={'display': 'flex', 'gap': '1rem', 'marginBottom': '1rem'}),
                                html.Div([
                                    dcc.Graph(id='huc2-volume-graph', style={'flex': '1', 'minWidth': '0'},
                                              responsive=True, config={'displayModeBar': False}),
                                    dcc.Graph(id='huc4-volume-graph', style={'flex': '1', 'minWidth': '0'},
                                              responsive=True, config={'displayModeBar': False}),
                                ], className='chart-pair',
                                   style={'display': 'flex', 'gap': '1rem'}),
                            ], style=_CARD_STYLE),
                            html.Div([
                                _drill_card_header('HUC6 Drill-down', 'snowpack-drill'),
                                html.Div([
                                    dcc.Graph(id='huc6-graph', style={'flex': '1', 'minWidth': '0'},
                                              responsive=True, config={'displayModeBar': False}),
                                    dcc.Graph(id='huc6-volume-graph', style={'flex': '1', 'minWidth': '0'},
                                              responsive=True, config={'displayModeBar': False}),
                                ], className='chart-pair',
                                   style={'display': 'flex', 'gap': '1rem'}),
                            ], style=_CARD_STYLE),
                            html.Div([
                                html.P([
                                    html.Strong('Data: '),
                                    datasets.get('snodas')['footnote'],
                                ], style={'margin': '0'}),
                            ], id='snowpack-footnote', style={
                                'fontSize': '0.75rem', 'color': '#666', 'lineHeight': '1.5',
                                'borderTop': '1px solid #ddd', 'paddingTop': '0.6rem',
                            }),
                        ], style={'padding': '1rem'}),
                    ]),
                    dcc.Tab(label='Trends', value='trends', children=[
                        html.Div([
                            html.P(
                                'Showing current water year data',
                                style={'fontSize': '0.85rem', 'color': '#555',
                                       'margin': '0 0 0.75rem 0'},
                            ),
                            dcc.Graph(id='basin-timeseries-graph', className='timeseries-graph',
                                      style={'height': '45vh'}, responsive=True,
                                      config={'displayModeBar': False}),
                            dcc.Graph(id='huc4-timeseries-graph', className='timeseries-graph',
                                      style={'height': '45vh'}, responsive=True,
                                      config={'displayModeBar': False}),
                            html.Div([
                                _drill_card_header('HUC6 Drill-down', 'trends-drill'),
                                dcc.Graph(id='huc6-timeseries-graph', className='timeseries-graph',
                                          style={'height': '45vh'}, responsive=True,
                                          config={'displayModeBar': False}),
                            ], style={**_CARD_STYLE, 'marginTop': '1rem'}),
                        ], style={'padding': '1rem'}),
                    ]),
                    dcc.Tab(label='Historical', value='historical', children=[
                        html.Div([
                            html.Div([
                                html.Label('Basin', style={'fontWeight': 'bold',
                                           'fontSize': '0.85rem', 'marginRight': '0.5rem'}),
                                dcc.Dropdown(
                                    id='historical-basin',
                                    options=[{'label': 'Columbia River Basin',
                                              'value': '17'}],
                                    value='17',
                                    clearable=False,
                                    style={'width': '320px', 'fontSize': '0.85rem'},
                                ),
                            ], style={'display': 'flex', 'alignItems': 'center',
                                      'marginBottom': '0.6rem'}),
                            html.Div(id='historical-summary',
                                     style={'fontSize': '0.85rem', 'color': '#555',
                                            'marginBottom': '0.5rem', 'minHeight': '1.2rem'}),
                            dcc.Graph(id='climatology-graph', className='timeseries-graph',
                                      style={'height': '60vh'}, responsive=True,
                                      config={'displayModeBar': False}),
                            html.Div([
                                html.P([
                                    'Shaded bands show the historical distribution across all '
                                    'available water years (widest = min–max, then 10–90th and '
                                    '25–75th percentiles); the dashed line is the daily median and '
                                    'the bold orange line is the current water year. Percentiles '
                                    'align on day-of-water-year (Feb 29 omitted).',
                                ], style={'margin': '0'}),
                            ], style={
                                'fontSize': '0.75rem', 'color': '#666', 'lineHeight': '1.5',
                                'borderTop': '1px solid #ddd', 'paddingTop': '0.6rem',
                                'marginTop': '0.5rem',
                            }),
                        ], style={'padding': '1rem'}),
                    ]),
                ]),
            ], className='chart-area', style={'flex': '1', 'padding': '1.2rem', 'overflowY': 'auto'}),

        ], className='body-row', style={'display': 'flex', 'flex': '1', 'overflow': 'hidden'}),

    ], style={
        'display': 'flex', 'flexDirection': 'column',
        'height': '100vh', 'fontFamily': 'sans-serif', 'background': '#f5f5f5',
    })
