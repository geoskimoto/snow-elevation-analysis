from werkzeug.middleware.proxy_fix import ProxyFix

from app import server  # noqa: F401 — gunicorn entrypoint

server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1)
