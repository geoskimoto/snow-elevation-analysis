from datetime import date

from dash import dcc, html


def get_layout() -> html.Div:
    today = date.today().isoformat()
    return html.Div([
        dcc.Store(id='result-store'),
        dcc.Download(id='download-data'),

        # Header bar
        html.Div([
            html.H2('Snow Elevation Analysis',
                    style={'margin': '0', 'color': '#333', 'fontSize': '1.2rem'}),
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
                        },
                    ),
                ], id='download-section', style={'display': 'none'}),
            ], style={
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
                                dcc.Graph(id='huc2-graph', style={'flex': '1', 'minWidth': '0'}),
                                dcc.Graph(id='huc4-graph', style={'flex': '1', 'minWidth': '0'}),
                            ], style={'display': 'flex', 'gap': '1rem', 'marginBottom': '1rem'}),
                            html.Div([
                                dcc.Graph(id='huc2-volume-graph', style={'flex': '1', 'minWidth': '0'}),
                                dcc.Graph(id='huc4-volume-graph', style={'flex': '1', 'minWidth': '0'}),
                            ], style={'display': 'flex', 'gap': '1rem'}),
                        ], style={'padding': '1rem'}),
                    ]),
                    dcc.Tab(label='Trends', value='trends', children=[
                        html.Div([
                            html.P(
                                'Showing current water year data',
                                style={'fontSize': '0.85rem', 'color': '#555',
                                       'margin': '0 0 0.75rem 0'},
                            ),
                            dcc.Graph(id='basin-timeseries-graph',
                                      style={'height': '45vh'}),
                            dcc.Graph(id='huc4-timeseries-graph',
                                      style={'height': '45vh'}),
                        ], style={'padding': '1rem'}),
                    ]),
                ]),
            ], style={'flex': '1', 'padding': '1.2rem', 'overflowY': 'auto'}),

        ], style={'display': 'flex', 'flex': '1', 'overflow': 'hidden'}),

    ], style={
        'display': 'flex', 'flexDirection': 'column',
        'height': '100vh', 'fontFamily': 'sans-serif', 'background': '#f5f5f5',
    })
