from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create SQLAlchemy base class
Base = declarative_base()

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