"""SQLAlchemy engine for the registry (PostgreSQL via psycopg 3).

The connection string comes from ``SFAC_DB_URL`` (environment or ``.env``). It contains a
password, so it is **never** logged or put into an exception message: errors name the
variable, the failure class and (for connection failures) nothing else.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, DBAPIError, SQLAlchemyError

from strategy_factory.core.env import resolve_env
from strategy_factory.core.errors import RegistryError

DB_URL_ENV = "SFAC_DB_URL"
DEFAULT_CONNECT_TIMEOUT_S = 10  # infrastructure default (fail fast instead of hanging)


def db_url() -> str:
    """``SFAC_DB_URL`` from the environment or ``.env``; ``RegistryError`` if missing."""
    value, _ = resolve_env((DB_URL_ENV,))[DB_URL_ENV]
    if not value:
        raise RegistryError(
            f"{DB_URL_ENV} is not set: define it in the environment or in .env (see .env.example)",
            stage="registry",
        )
    return value


def make_engine(
    url: str | None = None,
    check: bool = True,
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
) -> Engine:
    """Engine for ``url`` (default ``SFAC_DB_URL``); ``check`` opens one connection first."""
    raw = url if url is not None else db_url()
    try:
        parsed = make_url(raw)
    except ArgumentError:
        raise RegistryError(
            f"{DB_URL_ENV} is not a valid database URL (value not shown)", stage="registry"
        ) from None
    if not parsed.drivername.startswith("postgresql"):
        raise RegistryError(
            f"{DB_URL_ENV} must be a postgresql URL (postgresql+psycopg://...)", stage="registry"
        )
    engine = create_engine(
        parsed,
        hide_parameters=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": connect_timeout},
    )
    if check:
        check_connection(engine)
    return engine


def check_connection(engine: Engine) -> None:
    """Open one connection; unreachable database -> ``RegistryError`` without the URL."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except (DBAPIError, SQLAlchemyError, OSError) as exc:
        kind = type(getattr(exc, "orig", None) or exc).__name__
        raise RegistryError(
            f"cannot connect to the registry database ({kind}); is it running "
            "(`docker compose up -d`) and is SFAC_DB_URL correct? (URL not shown)",
            stage="registry",
        ) from None
