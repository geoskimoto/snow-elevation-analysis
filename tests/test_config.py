import pytest
import importlib
import sys


def _reload_config(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if 'config' in sys.modules:
        del sys.modules['config']
    import config
    return config


def test_get_password_hash_returns_value(monkeypatch):
    monkeypatch.setenv('DASH_PASSWORD_HASH', '$2b$12$testhash')
    cfg = _reload_config(monkeypatch, {})
    assert cfg.get_password_hash() == '$2b$12$testhash'


def test_get_password_hash_raises_if_missing(monkeypatch):
    monkeypatch.delenv('DASH_PASSWORD_HASH', raising=False)
    cfg = _reload_config(monkeypatch, {'SECRET_KEY': 'k'})
    with pytest.raises(RuntimeError, match='DASH_PASSWORD_HASH'):
        cfg.get_password_hash()


def test_get_secret_key_returns_value(monkeypatch):
    cfg = _reload_config(monkeypatch, {'SECRET_KEY': 'mysecret', 'DASH_PASSWORD_HASH': 'h'})
    assert cfg.get_secret_key() == 'mysecret'


def test_get_secret_key_raises_if_missing(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    cfg = _reload_config(monkeypatch, {'DASH_PASSWORD_HASH': 'h'})
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        cfg.get_secret_key()


def test_get_session_lifetime_hours_default(monkeypatch):
    monkeypatch.delenv('SESSION_LIFETIME_HOURS', raising=False)
    cfg = _reload_config(monkeypatch, {'DASH_PASSWORD_HASH': 'h', 'SECRET_KEY': 'k'})
    assert cfg.get_session_lifetime_hours() == 8


def test_get_session_lifetime_hours_custom(monkeypatch):
    cfg = _reload_config(monkeypatch, {
        'DASH_PASSWORD_HASH': 'h', 'SECRET_KEY': 'k', 'SESSION_LIFETIME_HOURS': '4'
    })
    assert cfg.get_session_lifetime_hours() == 4


def test_get_cache_dir_default(monkeypatch):
    monkeypatch.delenv('CACHE_DIR', raising=False)
    cfg = _reload_config(monkeypatch, {'DASH_PASSWORD_HASH': 'h', 'SECRET_KEY': 'k'})
    assert str(cfg.get_cache_dir()) == 'data/cache'


def test_get_output_dir_default(monkeypatch):
    monkeypatch.delenv('OUTPUT_DIR', raising=False)
    cfg = _reload_config(monkeypatch, {'DASH_PASSWORD_HASH': 'h', 'SECRET_KEY': 'k'})
    assert str(cfg.get_output_dir()) == 'output'
