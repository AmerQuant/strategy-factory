"""Registry test fixtures: one throw-away PostgreSQL schema per test, migrated with Alembic.

DB tests are marked ``@pytest.mark.db``. Without a reachable database (``SFAC_DB_URL``,
``docker compose up -d``) they are skipped with a clear reason; CI fails on any skipped
``db`` test.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from strategy_factory.core.errors import RegistryError
from strategy_factory.registry.engine import db_url, make_engine
from strategy_factory.registry.migrations import upgrade

SKIP_REASON = (
    "registry database not reachable ({why}); start it with `docker compose up -d` and set "
    "SFAC_DB_URL (CI fails on skipped db tests)"
)


def schema_url(schema: str) -> URL:
    """``SFAC_DB_URL`` with ``search_path`` pinned to ``schema`` (psycopg ``options``)."""
    return make_url(db_url()).update_query_dict({"options": f"-csearch_path={schema}"})


_UNREACHABLE: list[str] = []  # cached skip reason (checked once per session)


def _admin_engine() -> Engine:
    if _UNREACHABLE:
        pytest.skip(_UNREACHABLE[0])
    try:
        return make_engine(connect_timeout=3)
    except RegistryError as exc:
        _UNREACHABLE.append(SKIP_REASON.format(why=str(exc).split(";")[0]))
        pytest.skip(_UNREACHABLE[0])


@pytest.fixture
def registry_schema() -> Iterator[str]:
    """Create an empty schema, yield its name, drop it (CASCADE) afterwards."""
    admin = _admin_engine()
    schema = f"t_{uuid.uuid4().hex[:16]}"
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield schema
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def registry_engine(registry_schema: str) -> Iterator[Engine]:
    """Engine bound to the test schema, migrated to head."""
    engine = create_engine(schema_url(registry_schema), hide_parameters=True)
    upgrade(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def second_engine(registry_schema: str, registry_engine: Engine) -> Iterator[Engine]:
    """A separate engine (own connection pool) on the same schema."""
    engine = create_engine(schema_url(registry_schema), hide_parameters=True)
    try:
        yield engine
    finally:
        engine.dispose()
