from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create SQLAlchemy base class
Base = declarative_base()

# Create SQLAlchemy engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True if settings.DEBUG else False,
    future=True
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