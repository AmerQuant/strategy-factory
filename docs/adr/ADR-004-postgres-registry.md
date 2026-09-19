# ADR-004: PostgreSQL registry with SQLAlchemy Core, psycopg 3, Alembic and COPY batching

- **Status:** Accepted
- **Date:** 2026-09-19

## Decision

رجیستری PostgreSQL در Docker؛ SQLAlchemy Core + psycopg 3 + Alembic؛ نوشتن دسته‌ای با COPY

_English:_ Trial registry in PostgreSQL (Docker), accessed with SQLAlchemy Core + psycopg 3, migrated with Alembic; bulk writes via COPY.

_Source: design document v1.0, §14 (decision log); rationale in §2._
