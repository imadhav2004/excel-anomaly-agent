"""Connecting to the database.

Which database is used is decided by ONE setting, DATABASE_URL (in .env or Streamlit secrets):
  not set                                          -> a SQLite file, data/app.db (nothing to install)
  postgresql://user:password@localhost:5432/name   -> PostgreSQL
The rest of the program never knows which one it is: SQLAlchemy hides the difference.
"""
import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from anomaly_agent.db.models import Base

DEFAULT_URL = "sqlite:///data/app.db"
_engines = {}  # one engine per URL, created the first time it is needed


class DatabaseUnavailable(Exception):
    """The database could not be reached. The message is safe to show (it never contains the password)."""


def normalise_url(url):
    """Accept the usual PostgreSQL spellings and pick the psycopg driver for them."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def database_url():
    load_dotenv()  # does not replace a value that is already set in the environment
    return normalise_url(os.getenv("DATABASE_URL") or DEFAULT_URL)


def safe_url(url):
    """The URL with the password hidden, for messages."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "the database"


def get_engine(url=None):
    url = url or database_url()
    if url not in _engines:
        options = {}
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite":
            if parsed.database and parsed.database != ":memory:":
                Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
            options["connect_args"] = {"check_same_thread": False}  # Streamlit uses several threads
        else:
            options["pool_pre_ping"] = True  # drop connections that the server closed
        try:
            engine = create_engine(url, **options)
            Base.metadata.create_all(engine)  # creates missing tables, leaves existing ones alone
        except SQLAlchemyError as error:
            reason = str(getattr(error, "orig", error)).strip().splitlines()[0]
            raise DatabaseUnavailable(f"Cannot connect to {safe_url(url)}: {reason}") from None
        _engines[url] = engine
    return _engines[url]


def dispose_engines():
    """Close every connection. Tests call this so temporary database files can be deleted."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


@contextmanager
def session_scope(url=None):
    """One unit of work: everything is saved together, or (on an error) nothing is saved."""
    session = sessionmaker(bind=get_engine(url), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
