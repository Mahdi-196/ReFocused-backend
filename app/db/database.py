from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings


# Create SQLAlchemy engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Disable DB logging for performance
    future=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=True  # Validate connections before use
)

# Create SessionLocal class
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    """Dependency function that yields db sessions"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

def get_db_session():
    """Context manager for database sessions (for background tasks)"""
    return async_session()

# Create synchronous engine for background tasks that can't use async
sync_database_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
sync_engine = create_engine(
    sync_database_url,
    echo=False,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=True
)

# Create synchronous session factory
sync_session = sessionmaker(bind=sync_engine) 