from collections.abc import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import get_settings
from backend.models import Base

logger = logging.getLogger(__name__)
settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create tables from metadata only in non-production when enabled.

    Production and Docker always rely on `alembic upgrade head` before uvicorn starts.
    """
    if not settings.should_auto_create_tables:
        logger.info(
            "Skipping create_all (environment=%s auto_create_tables=%s)",
            settings.environment,
            settings.auto_create_tables,
        )
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
