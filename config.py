import os
from pathlib import Path


def get_password_hash() -> str:
    v = os.environ.get('DASH_PASSWORD_HASH', '')
    if not v:
        raise RuntimeError("Required environment variable 'DASH_PASSWORD_HASH' is not set")
    return v


def get_secret_key() -> str:
    v = os.environ.get('SECRET_KEY', '')
    if not v:
        raise RuntimeError("Required environment variable 'SECRET_KEY' is not set")
    return v


def get_session_lifetime_hours() -> int:
    return int(os.environ.get('SESSION_LIFETIME_HOURS', '8'))


def get_cache_dir() -> Path:
    return Path(os.environ.get('CACHE_DIR', 'data/cache'))


def get_output_dir() -> Path:
    return Path(os.environ.get('OUTPUT_DIR', 'output'))
