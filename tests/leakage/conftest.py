"""Fixtures shared by the leakage tests (registry DB fixtures live in tests/fixtures)."""

from fixtures.registry_db import registry_engine, registry_schema, second_engine

__all__ = ["registry_engine", "registry_schema", "second_engine"]
