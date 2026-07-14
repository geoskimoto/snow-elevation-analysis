"""Local dev runner for the Snow Elevation Analysis Dash app.

Mirrors app.create_app() but SKIPS streamflows_auth.protect_app, which is
deployment-only and absent from a bare checkout. DEV ONLY — no authentication;
never use this to serve the app in production (use gunicorn wsgi:server, which
keeps the auth layer).

Self-contained: puts the repo root on sys.path so it runs from anywhere.
"""
import os
import sys
from pathlib import Path

# repo root = three levels up from .claude/skills/run-app/dev_server.py
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)  # so relative CACHE_DIR (data/cache) resolves

# Required by config.py; dummy values are fine without the auth wrapper.
os.environ.setdefault('SECRET_KEY', 'dev-secret-key')
os.environ.setdefault('DASH_PASSWORD_HASH', 'x')

import diskcache
from dash import Dash, DiskcacheManager

import callbacks
import config
import layout

PORT = int(os.environ.get('PORT', '8050'))


def build_app() -> Dash:
    cache_dir = config.get_cache_dir() / 'diskcache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    manager = DiskcacheManager(diskcache.Cache(str(cache_dir)))
    app = Dash(__name__, background_callback_manager=manager,
               suppress_callback_exceptions=True)
    app.layout = layout.get_layout()
    callbacks.register(app)
    return app


if __name__ == '__main__':
    build_app().run(host='127.0.0.1', port=PORT, debug=False)
