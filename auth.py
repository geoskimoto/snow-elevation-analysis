import bcrypt
from flask import session


def check_password(password: str, hashed: str) -> bool:
    if not password:
        return False
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def is_authenticated() -> bool:
    return bool(session.get('authed'))


def set_authenticated(value: bool) -> None:
    session['authed'] = value
    session.permanent = value
