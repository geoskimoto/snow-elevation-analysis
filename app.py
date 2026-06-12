from datetime import timedelta

from flask import Flask, request, redirect, session, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import auth
import config

_LOGIN_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Snow Elevation Analysis — Login</title>
  <style>
    body{font-family:sans-serif;display:flex;justify-content:center;
         align-items:center;height:100vh;margin:0;background:#f5f5f5;}
    .box{background:white;padding:2rem;border-radius:8px;
         box-shadow:0 2px 8px rgba(0,0,0,.1);width:300px;}
    h2{margin-top:0;color:#333;}
    input[type=password]{width:100%;padding:.5rem;margin:.5rem 0 1rem;
                         box-sizing:border-box;border:1px solid #ccc;border-radius:4px;}
    button{width:100%;padding:.6rem;background:#0072B2;color:white;
           border:none;border-radius:4px;cursor:pointer;font-size:1rem;}
    button:hover{background:#005a8e;}
    .error{color:#D55E00;margin-bottom:.8rem;font-size:.9rem;}
  </style>
</head>
<body>
  <div class="box">
    <h2>Snow Elevation Analysis</h2>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="POST" action="/login">
      <label for="password">Password</label>
      <input type="password" name="password" id="password" autofocus autocomplete="current-password">
      <button type="submit">Sign in</button>
    </form>
  </div>
</body>
</html>"""


def create_server() -> Flask:
    server = Flask(__name__)
    server.secret_key = config.get_secret_key()
    server.config['SESSION_COOKIE_HTTPONLY'] = True
    server.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    server.config['SESSION_COOKIE_SECURE'] = True
    server.permanent_session_lifetime = timedelta(
        hours=config.get_session_lifetime_hours()
    )

    limiter = Limiter(
        get_remote_address,
        app=server,
        default_limits=[],
        storage_uri='memory://',
    )

    @server.route('/login', methods=['GET'])
    def login_get():
        return render_template_string(_LOGIN_HTML, error=None)

    @server.route('/login', methods=['POST'])
    @limiter.limit('5 per 15 minutes')
    def login_post():
        pw = request.form.get('password', '')
        if auth.check_password(pw, config.get_password_hash()):
            auth.set_authenticated(True)
            return redirect('/')
        return render_template_string(_LOGIN_HTML, error='Invalid password'), 401

    @server.route('/logout')
    def logout():
        session.clear()
        return redirect('/login')

    @server.before_request
    def require_login():
        if request.path == '/login':
            return
        if not auth.is_authenticated():
            return redirect('/login')

    return server
