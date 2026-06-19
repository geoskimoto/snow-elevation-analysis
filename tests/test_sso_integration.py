"""SSO integration tests for snow-elevation app."""
import os
import pytest
import jwt as pyjwt
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest-32bytes!!")
os.environ.setdefault("AUTH_LOGIN_URL", "https://apps.streamflows.org/login")
os.environ.setdefault("AUTH_PORTAL_URL", "https://apps.streamflows.org/")
os.environ.setdefault("CACHE_DIR", "/tmp/snow_elevation_test_cache")
os.environ.setdefault("OUTPUT_DIR", "/tmp/snow_elevation_test_output")

from app import server


SECRET = "test-jwt-secret-for-pytest-32bytes!!"


def make_token(groups):
    payload = {
        "sub": "testuser",
        "groups": groups,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


@pytest.fixture
def client():
    server.config["TESTING"] = True
    server.config["SERVER_NAME"] = "streamflows.org"
    with server.test_client() as c:
        yield c


def test_unauthenticated_redirects_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "apps.streamflows.org/login" in resp.headers["Location"]


def test_valid_streamflow_token_allows_access(client):
    token = make_token(["streamflow"])
    client.set_cookie("streamflows_auth", token, domain=".streamflows.org")
    resp = client.get("/")
    assert resp.status_code == 200


def test_wrong_group_redirects_to_portal(client):
    token = make_token(["econ"])
    client.set_cookie("streamflows_auth", token, domain=".streamflows.org")
    resp = client.get("/")
    assert resp.status_code == 302
    assert "apps.streamflows.org" in resp.headers["Location"]


def test_admin_group_bypasses_required_group(client):
    token = make_token(["admin"])
    client.set_cookie("streamflows_auth", token, domain=".streamflows.org")
    resp = client.get("/")
    assert resp.status_code == 200


def test_expired_token_redirects_to_login(client):
    payload = {
        "sub": "testuser",
        "groups": ["streamflow"],
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = pyjwt.encode(payload, SECRET, algorithm="HS256")
    client.set_cookie("streamflows_auth", token, domain=".streamflows.org")
    resp = client.get("/")
    assert resp.status_code == 302
    assert "apps.streamflows.org/login" in resp.headers["Location"]


def test_invalid_token_redirects_to_login(client):
    client.set_cookie("streamflows_auth", "not.a.valid.token", domain=".streamflows.org")
    resp = client.get("/")
    assert resp.status_code == 302
    assert "apps.streamflows.org/login" in resp.headers["Location"]


def test_dash_routes_exempt(client):
    resp = client.get("/_dash-layout")
    assert resp.status_code != 302


def test_assets_route_exempt(client):
    resp = client.get("/assets/style.css")
    assert resp.status_code != 302
