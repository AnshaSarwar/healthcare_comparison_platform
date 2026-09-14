from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base

# Dedicated scratch database on the same local Postgres instance used for dev
# (infra/docker-compose.yml). Never points at `benefits_compare` (the real dev DB) so
# seed tests can freely drop/recreate tables without touching anyone's local data.
_MAINTENANCE_DSN = "postgresql://benefits:benefits@localhost:5432/postgres"
_TEST_DB_NAME = "benefits_compare_seedtest"
_TEST_DATABASE_URL = f"postgresql+asyncpg://benefits:benefits@localhost:5432/{_TEST_DB_NAME}"


async def _recreate_test_database() -> None:
    conn = await asyncpg.connect(_MAINTENANCE_DSN)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            _TEST_DB_NAME,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"')
        await conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def seed_database_url() -> str:
    """Provisions `benefits_compare_seedtest` once per test session, empty."""
    asyncio.run(_recreate_test_database())
    return _TEST_DATABASE_URL


@pytest.fixture
async def seed_session(seed_database_url: str) -> AsyncIterator[AsyncSession]:
    """A clean-schema session against the scratch DB, isolated per test function."""
    engine = create_async_engine(seed_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
