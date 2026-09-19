"""Alembic environment for the registry.

The URL is never written to alembic.ini or logged: a caller can pass an open SQLAlchemy
connection via ``config.attributes["connection"]`` (used by ``sfac db`` and the tests);
otherwise the engine is built from ``SFAC_DB_URL``. Offline (SQL script) mode is not used.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy.engine import Connection

from strategy_factory.registry.engine import make_engine
from strategy_factory.registry.tables import metadata

config = context.config


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine()
    with engine.begin() as conn:
        _run(conn)


if context.is_offline_mode():
    raise RuntimeError("offline Alembic mode is not supported for the registry; run online")
run_migrations_online()
