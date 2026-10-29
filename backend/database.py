"""SQLite engine/session plus a one-time guard for the pre-v2 schema."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings

SQLALCHEMY_DATABASE_URL = settings.database_url

_connect_args = {"check_same_thread": False}
_engine_kwargs: dict = {}
if SQLALCHEMY_DATABASE_URL in ("sqlite://", "sqlite:///:memory:"):
    _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_file() -> Path | None:
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def init_db() -> None:
    """Create all tables. A pre-v2 database (has `inventory`, no `store_profile`)
    is moved aside to `<name>.legacy` because v2 has no migrations."""
    import models  # noqa: F401  (register tables on Base)

    names = set(inspect(engine).get_table_names())
    path = _sqlite_file()
    if "inventory" in names and "store_profile" not in names and path and path.exists():
        engine.dispose()
        path.rename(path.with_suffix(path.suffix + ".legacy"))
    Base.metadata.create_all(bind=engine)
