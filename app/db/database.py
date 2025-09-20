from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse


# Sanitize DATABASE_URL for asyncpg: convert sslmode=require -> ssl=require
def _sanitize_asyncpg_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.scheme.startswith("postgresql+asyncpg"):
            query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
            changed = False
            new_pairs = []
            for k, v in query_pairs:
                if k == "sslmode":
                    k = "ssl"
                    changed = True
                new_pairs.append((k, v))
            if changed:
                new_query = urlencode(new_pairs)
                sanitized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
                logger.info("🔒 Adjusted DATABASE_URL query param: sslmode→ssl for asyncpg")
                return sanitized
    except Exception:
        pass
    return url

sanitized_database_url = _sanitize_asyncpg_url(settings.DATABASE_URL)

# Create SQLAlchemy engine
engine = create_async_engine(
    sanitized_database_url,
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
sync_database_url = sanitized_database_url.replace("postgresql+asyncpg://", "postgresql://")
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