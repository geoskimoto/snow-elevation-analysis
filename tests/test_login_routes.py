# Login route tests commented out — auth/login removed from app (2026-06-12)

# import bcrypt
# import pytest
# import sys
# from html.parser import HTMLParser
#
#
# def _make_hash(pw: str) -> str:
#     return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
#
#
# def _get_csrf_token(client) -> str:
#     """GET /login and extract the hidden csrf_token input value."""
#     resp = client.get('/login')
#
#     class _Parser(HTMLParser):
#         token = ''
#         def handle_starttag(self, tag, attrs):
#             if tag == 'input':
#                 d = dict(attrs)
#                 if d.get('name') == 'csrf_token':
#                     self.token = d.get('value', '')
#
#     p = _Parser()
#     p.feed(resp.data.decode())
#     return p.token
#
#
# @pytest.fixture
# def client(monkeypatch):
#     monkeypatch.setenv('DASH_PASSWORD_HASH', _make_hash('testpass'))
#     monkeypatch.setenv('SECRET_KEY', 'testsecretkey123')
#     for mod in list(sys.modules.keys()):
#         if mod in ('app', 'config', 'auth'):
#             del sys.modules[mod]
#     from app import create_server
#     server = create_server()
#     server.config['TESTING'] = True
#     server.config['SESSION_COOKIE_SECURE'] = False
#     with server.test_client() as c:
#         yield c
#
#
# def test_login_page_loads(client):
#     resp = client.get('/login')
#     assert resp.status_code == 200
#     assert b'password' in resp.data.lower()
#
#
# def test_login_page_includes_csrf_token(client):
#     token = _get_csrf_token(client)
#     assert len(token) == 64  # secrets.token_hex(32) = 64 hex chars
#
#
# def test_correct_password_redirects_to_root(client):
#     token = _get_csrf_token(client)
#     resp = client.post('/login', data={'password': 'testpass', 'csrf_token': token},
#                        follow_redirects=False)
#     assert resp.status_code == 302
#     assert resp.headers['Location'] == '/'
#
#
# def test_wrong_password_returns_401(client):
#     token = _get_csrf_token(client)
#     resp = client.post('/login', data={'password': 'wrongpass', 'csrf_token': token})
#     assert resp.status_code == 401
#     assert b'invalid password' in resp.data.lower()
#
#
# def test_missing_csrf_token_returns_400(client):
#     resp = client.post('/login', data={'password': 'testpass'})
#     assert resp.status_code == 400
#
#
# def test_wrong_csrf_token_returns_400(client):
#     _get_csrf_token(client)  # sets session['csrf_token']
#     resp = client.post('/login', data={'password': 'testpass', 'csrf_token': 'invalid'})
#     assert resp.status_code == 400
#
#
# def test_unauthenticated_root_redirects_to_login(client):
#     resp = client.get('/', follow_redirects=False)
#     assert resp.status_code == 302
#     assert '/login' in resp.headers['Location']
#
#
# def test_logout_clears_session_and_redirects(client):
#     token = _get_csrf_token(client)
#     client.post('/login', data={'password': 'testpass', 'csrf_token': token})
#     resp = client.get('/logout', follow_redirects=False)
#     assert resp.status_code == 302
#     assert '/login' in resp.headers['Location']
#     resp2 = client.get('/', follow_redirects=False)
#     assert resp2.status_code == 302
#
#
# def test_authenticated_root_not_redirected(client):
#     token = _get_csrf_token(client)
#     client.post('/login', data={'password': 'testpass', 'csrf_token': token})
#     resp = client.get('/', follow_redirects=False)
#     assert resp.status_code != 302
