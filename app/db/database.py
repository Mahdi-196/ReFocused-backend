from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# Create SQLAlchemy base class
Base = declarative_base()

# Create SQLAlchemy engine with optimized connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True if settings.DEBUG else False,
    future=True,
    # Connection pool settings
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=True,  # Verify connections before use
)

# Create SessionLocal class with optimized settings
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def get_db():
    """
    Dependency function that yields db sessions.
    This uses the connection pool for efficient connection management.
    The session automatically closes after the request is complete.
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close() 