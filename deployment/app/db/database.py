from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import logging
import os
import time
import asyncio
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from app.core.config import settings

# Configure logging for database connections
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Enhanced database connection debugging for Lambda
logger.info(f"🔗 DATABASE CONNECTION SETUP:")
logger.info(f"📍 Environment: AWS_LAMBDA_FUNCTION_NAME={os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'None')}")
logger.info(f"📍 AWS Region: {os.getenv('AWS_REGION', 'unknown')}")
logger.info(f"📍 VPC ID: {os.getenv('VPC_ID', 'unknown')}")
logger.info(f"📍 Subnet IDs: {os.getenv('SUBNET_IDS', 'unknown')}")
logger.info(f"📍 Security Group: {os.getenv('SECURITY_GROUP_ID', 'unknown')}")
logger.info(f"🌐 DATABASE_URL: {settings.DATABASE_URL[:50]}...")  # Log first 50 chars for security
logger.info(f"🏊 Pool Config: size={settings.DATABASE_POOL_SIZE}, max_overflow={settings.DATABASE_MAX_OVERFLOW}")
logger.info(f"⏰ Timeouts: pool_timeout={settings.DATABASE_POOL_TIMEOUT}, pool_recycle={settings.DATABASE_POOL_RECYCLE}")
logger.info(f"🔍 Engine creation starting at: {time.time()}")

# VPC and network analysis
if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
    logger.info(f"🔍 LAMBDA VPC ANALYSIS:")
    if not os.getenv('VPC_ID'):
        logger.warning(f"⚠️ VPC_ID not set - Lambda may not be in VPC")
    if not os.getenv('SUBNET_IDS'):
        logger.warning(f"⚠️ SUBNET_IDS not set - Lambda subnet configuration unknown")
    if 'localhost' in settings.DATABASE_URL or '127.0.0.1' in settings.DATABASE_URL:
        logger.error(f"❌ DATABASE_URL contains localhost - this will not work in Lambda VPC")
    if not settings.DATABASE_URL.startswith('postgresql+asyncpg://'):
        logger.warning(f"⚠️ DATABASE_URL should use 'postgresql+asyncpg://' for async operations")

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

# Create SQLAlchemy engine with enhanced error handling
try:
    engine_start_time = time.time()
    logger.info(f"🔧 ENGINE CREATION: Starting async engine setup...")

    # Enhanced connect_args for better debugging and timeout handling
    connect_args = {
        "server_settings": {
            "application_name": "ReFocused-Lambda",
            "log_statement": "all",  # Log all SQL statements
            "log_duration": "on",   # Log query duration
        },
        "timeout": 15,  # Connection timeout (reduced from 30)
        "command_timeout": 20,  # Query timeout (reduced from 30)
    }

    # Add SSL configuration for production
    if not ('localhost' in sanitized_database_url or '127.0.0.1' in sanitized_database_url):
        # asyncpg expects 'ssl', not 'sslmode'
        connect_args["ssl"] = "require"
        logger.info(f"🔒 SSL: Enabled for production database connection")

    logger.info(f"🔧 ENGINE PARAMS: pool_size={settings.DATABASE_POOL_SIZE}, max_overflow={settings.DATABASE_MAX_OVERFLOW}")
    logger.info(f"🔧 ENGINE TIMEOUTS: pool_timeout={settings.DATABASE_POOL_TIMEOUT}s, connect_timeout=15s, query_timeout=20s")

    engine = create_async_engine(
        sanitized_database_url,
        echo=True,  # Enable DB logging for debugging
        future=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_pre_ping=True,  # Validate connections before use
        connect_args=connect_args
    )

    engine_creation_time = time.time() - engine_start_time
    logger.info(f"✅ ENGINE CREATED: Successfully created in {engine_creation_time:.2f} seconds")

    if engine_creation_time > 5.0:
        logger.warning(f"🐌 SLOW ENGINE CREATION: {engine_creation_time:.2f}s - may indicate network issues")

except Exception as e:
    engine_error_time = time.time() - engine_start_time
    logger.error(f"💥 ENGINE CREATION FAILED: After {engine_error_time:.2f}s - {str(e)}")
    logger.exception("ENGINE CREATION EXCEPTION DETAILS:")

    # Enhanced error analysis
    if "timeout" in str(e).lower():
        logger.error(f"🔍 ERROR ANALYSIS: Timeout error - likely VPC routing or NAT gateway issue")
    elif "connection" in str(e).lower():
        logger.error(f"🔍 ERROR ANALYSIS: Connection error - check VPC configuration and security groups")
    elif "authentication" in str(e).lower():
        logger.error(f"🔍 ERROR ANALYSIS: Authentication error - check DATABASE_URL credentials")
    else:
        logger.error(f"🔍 ERROR ANALYSIS: Unknown engine creation error")

    raise

# Create SessionLocal class with enhanced configuration
logger.info(f"🔧 SESSION FACTORY: Creating async session factory...")
try:
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False
    )
    logger.info(f"✅ SESSION FACTORY: Async session factory created successfully")
except Exception as e:
    logger.error(f"💥 SESSION FACTORY FAILED: {str(e)}")
    logger.exception("SESSION FACTORY EXCEPTION DETAILS:")
    raise

async def get_db():
    """Dependency function that yields db sessions with enhanced debugging"""
    import asyncio
    import os
    session_start_time = time.time()
    session_id = f"sess_{int(session_start_time * 1000) % 10000}"

    logger.info(f"🔗 DB SESSION START [{session_id}]: Creating new database session")
    logger.info(f"🔗 DB SESSION ENV [{session_id}]: Lambda={os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'None')}, VPC={os.getenv('VPC_ID', 'unknown')}")

    # Create session outside the try block so it's available in finally
    session = None
    try:
        logger.info(f"🔗 DB SESSION CREATE [{session_id}]: Calling async_session()...")
        session_create_start = time.time()
        session = async_session()
        session_creation_time = time.time() - session_create_start

        logger.info(f"✅ DB SESSION CREATED [{session_id}]: Session object created in {session_creation_time:.3f}s")

        if session_creation_time > 3.0:
            logger.warning(f"🐌 SLOW DB SESSION CREATION [{session_id}]: {session_creation_time:.2f}s - possible connection pool exhaustion")

        # Test connection with enhanced error handling and timeout
        logger.info(f"🔗 DB CONNECTION TEST [{session_id}]: Testing database connectivity...")
        test_start_time = time.time()
        from sqlalchemy import text

        try:
            # Execute test query with timeout wrapper
            logger.info(f"🔗 DB QUERY START [{session_id}]: SELECT 1")
            result = await asyncio.wait_for(
                session.execute(text("SELECT 1")),
                timeout=15.0  # 15 second timeout for connectivity test
            )
            test_value = result.scalar()
            test_time = time.time() - test_start_time

            if test_value == 1:
                logger.info(f"✅ DB CONNECTION OK [{session_id}]: Connectivity verified in {test_time:.3f}s")
            else:
                logger.error(f"❌ DB CONNECTION INVALID [{session_id}]: Expected 1, got {test_value}")
                raise Exception(f"Database connectivity test failed: expected 1, got {test_value}")

            if test_time > 5.0:
                logger.warning(f"🐌 SLOW DB CONNECTION TEST [{session_id}]: {test_time:.2f}s - possible VPC/NAT gateway latency")

        except asyncio.TimeoutError:
            test_timeout_time = time.time() - test_start_time
            logger.error(f"⏰ DB CONNECTION TIMEOUT [{session_id}]: Query timed out after {test_timeout_time:.2f}s")
            logger.error(f"⏰ DB TIMEOUT ANALYSIS [{session_id}]: This indicates VPC routing, NAT gateway, or database connectivity issues")
            raise Exception(f"Database connectivity test timed out after {test_timeout_time:.2f}s")

        except Exception as test_error:
            test_error_time = time.time() - test_start_time
            logger.error(f"❌ DB CONNECTION TEST FAILED [{session_id}]: {test_error_time:.2f}s - {str(test_error)}")
            logger.exception(f"DB CONNECTION TEST EXCEPTION [{session_id}]:")
            raise

        total_session_time = time.time() - session_start_time
        logger.info(f"🔗 DB SESSION READY [{session_id}]: Total setup time {total_session_time:.3f}s")

        # Connection test passed, yield the session
        yield session

        # Log session completion
        session_duration = time.time() - session_start_time
        logger.info(f"🔗 DB SESSION COMPLETE [{session_id}]: Session used for {session_duration:.3f}s")

    except Exception as e:
        session_error_time = time.time() - session_start_time
        logger.error(f"💥 DB SESSION ERROR [{session_id}]: Failed after {session_error_time:.2f}s - {str(e)}")
        logger.exception(f"DB SESSION EXCEPTION DETAILS [{session_id}]:")

        # Enhanced error analysis
        if session_error_time < 1.0:
            logger.error(f"🔍 ERROR ANALYSIS [{session_id}]: Failed during session creation - likely connection pool issue")
        elif session_error_time < 15.0:
            logger.error(f"🔍 ERROR ANALYSIS [{session_id}]: Failed during connectivity test - likely VPC/database issue")
        else:
            logger.error(f"🔍 ERROR ANALYSIS [{session_id}]: Timeout during connectivity test - VPC routing or NAT gateway issue")

        # CRITICAL FIX: Rollback any pending transaction before closing
        if session is not None:
            try:
                logger.info(f"🔄 DB ROLLBACK [{session_id}]: Attempting rollback...")
                await session.rollback()
                logger.info(f"✅ DB ROLLBACK OK [{session_id}]: Rollback successful")
            except Exception as rollback_error:
                logger.error(f"⚠️ DB ROLLBACK FAILED [{session_id}]: {str(rollback_error)}")

        raise
    finally:
        if session is not None:
            try:
                logger.info(f"🔒 DB SESSION CLOSE [{session_id}]: Closing session...")
                close_start = time.time()
                await session.close()
                close_time = time.time() - close_start
                logger.info(f"✅ DB SESSION CLOSED [{session_id}]: Session closed in {close_time:.3f}s")

                if close_time > 2.0:
                    logger.warning(f"🐌 SLOW DB SESSION CLOSE [{session_id}]: {close_time:.2f}s")

            except Exception as close_error:
                logger.error(f"⚠️ DB SESSION CLOSE ERROR [{session_id}]: {str(close_error)}")
                logger.exception(f"DB SESSION CLOSE EXCEPTION [{session_id}]:")

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