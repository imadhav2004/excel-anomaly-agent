"""Accounts: registration, login, password change and account deletion.

No Streamlit here, only rules and database work, so everything can be tested without a browser.

Security choices (each one is a viva answer):
  * Passwords are never stored. We store a bcrypt hash: salted, deliberately slow to guess.
  * Wrong email and wrong password give the SAME message, so nobody can find out which emails exist.
  * After 5 wrong passwords the account is locked for 10 minutes, which slows down guessing.
  * All database access goes through SQLAlchemy with bound parameters, so text typed into a form
    can never become SQL (no SQL injection).
"""
import re
from datetime import timedelta
from math import ceil

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from anomaly_agent.db.models import User, utcnow

BCRYPT_ROUNDS = 12      # higher = slower for an attacker (and for us); tests lower it
MIN_PASSWORD = 8
MAX_PASSWORD_BYTES = 72  # bcrypt only reads the first 72 bytes
MAX_ATTEMPTS = 5
LOCK_MINUTES = 10
WRONG_LOGIN = "Wrong email or password."
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_dummy_hash = None


class AuthError(Exception):
    """A problem the person can fix. The message is shown on the page."""


def normalise_email(email):
    return (email or "").strip().lower()


def check_email(email):
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise AuthError("Please enter a valid email address.")


def check_password(password, email=""):
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"The password must have at least {MIN_PASSWORD} characters.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise AuthError("The password is too long (at most 72 bytes).")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise AuthError("The password needs at least one letter and one number.")
    if email and password.lower() == email.lower():
        raise AuthError("The password must not be the same as the email.")


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password, stored_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], stored_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def public_user(user):
    """What the page may keep about a user: never the hash."""
    return {"id": user.id, "name": user.name, "email": user.email}


def register_user(session, name, email, password):
    name = (name or "").strip()
    email = normalise_email(email)
    if len(name) < 2 or len(name) > 100:
        raise AuthError("Please enter your name (2 to 100 characters).")
    check_email(email)
    check_password(password, email)
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise AuthError("An account with this email already exists. Please log in.")
    user = User(name=name, email=email, password_hash=hash_password(password), last_login=utcnow())
    session.add(user)
    try:
        session.flush()
    except IntegrityError:  # two people registering the same email at the same moment
        session.rollback()
        raise AuthError("An account with this email already exists. Please log in.") from None
    return public_user(user)


def login(session, email, password, now=None):
    now = now or utcnow()
    email = normalise_email(email)
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        # Do the same slow work as for a real user, so the response time does not give the secret away.
        global _dummy_hash
        _dummy_hash = _dummy_hash or hash_password("not-a-real-password-1")
        verify_password(password, _dummy_hash)
        raise AuthError(WRONG_LOGIN)
    if user.locked_until and user.locked_until > now:
        minutes = ceil((user.locked_until - now).total_seconds() / 60)
        raise AuthError(f"Too many wrong attempts. Please try again in {minutes} minute(s).")
    if not verify_password(password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= MAX_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_attempts = 0
        session.commit()  # keep the count even though we now raise an error
        raise AuthError(WRONG_LOGIN)
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = now
    return public_user(user)


def change_password(session, user_id, current_password, new_password):
    user = session.get(User, user_id)
    if user is None or not verify_password(current_password, user.password_hash):
        raise AuthError("The current password is wrong.")
    check_password(new_password, user.email)
    user.password_hash = hash_password(new_password)


def delete_account(session, user_id, password):
    """Delete the user and, through the cascade, every analysis they saved."""
    user = session.get(User, user_id)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("The password is wrong, so the account was not deleted.")
    session.delete(user)
