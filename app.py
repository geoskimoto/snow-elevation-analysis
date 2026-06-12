import diskcache
from dash import Dash, DiskcacheManager
from flask import Flask

import callbacks
import config
import layout


def create_server() -> Flask:
    server = Flask(__name__)
    return server


def create_app() -> Dash:
    server = create_server()
    cache_dir = config.get_cache_dir() / 'diskcache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    dc = diskcache.Cache(str(cache_dir))
    manager = DiskcacheManager(dc)

    app = Dash(
        __name__,
        server=server,
        background_callback_manager=manager,
        suppress_callback_exceptions=True,
    )
    app.layout = layout.get_layout()
    callbacks.register(app)

    return app


app = create_app()
server = app.server
