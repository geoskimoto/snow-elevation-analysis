import bcrypt
import pytest
from flask import Flask, session


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.secret_key = 'testsecret'
    app.config['TESTING'] = True
    return app


def _make_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def test_check_password_correct():
    from auth import check_password
    hsh = _make_hash('correct')
    assert check_password('correct', hsh) is True


def test_check_password_wrong():
    from auth import check_password
    hsh = _make_hash('correct')
    assert check_password('wrong', hsh) is False


def test_check_password_empty_string():
    from auth import check_password
    hsh = _make_hash('correct')
    assert check_password('', hsh) is False


def test_is_authenticated_true(flask_app):
    from auth import is_authenticated, set_authenticated
    with flask_app.test_request_context():
        set_authenticated(True)
        assert is_authenticated() is True


def test_is_authenticated_false_when_no_session(flask_app):
    from auth import is_authenticated
    with flask_app.test_request_context():
        assert is_authenticated() is False


def test_set_authenticated_false(flask_app):
    from auth import is_authenticated, set_authenticated
    with flask_app.test_request_context():
        set_authenticated(True)
        set_authenticated(False)
        assert is_authenticated() is False
