import bcrypt
import pytest
import sys


def _make_hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('DASH_PASSWORD_HASH', _make_hash('testpass'))
    monkeypatch.setenv('SECRET_KEY', 'testsecretkey123')
    for mod in list(sys.modules.keys()):
        if mod in ('app', 'config', 'auth'):
            del sys.modules[mod]
    from app import create_server
    server = create_server()
    server.config['TESTING'] = True
    server.config['SESSION_COOKIE_SECURE'] = False
    with server.test_client() as c:
        yield c


def test_login_page_loads(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'password' in resp.data.lower()


def test_correct_password_redirects_to_root(client):
    resp = client.post('/login', data={'password': 'testpass'}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/'


def test_wrong_password_returns_401(client):
    resp = client.post('/login', data={'password': 'wrongpass'})
    assert resp.status_code == 401
    assert b'invalid password' in resp.data.lower()


def test_unauthenticated_root_redirects_to_login(client):
    resp = client.get('/', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_logout_clears_session_and_redirects(client):
    client.post('/login', data={'password': 'testpass'})
    resp = client.get('/logout', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
    resp2 = client.get('/', follow_redirects=False)
    assert resp2.status_code == 302


def test_authenticated_root_not_redirected(client):
    client.post('/login', data={'password': 'testpass'})
    resp = client.get('/', follow_redirects=False)
    assert resp.status_code != 302
