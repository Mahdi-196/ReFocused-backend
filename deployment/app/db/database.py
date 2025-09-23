from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
import logging
import os
import time
import asyncio
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from app.core.config import settings
import socket
import ssl
import contextlib

# Configure logging for database connections
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def _mask_url_credentials(url: str) -> str:
    try:
        p = urlparse(url)
        userinfo = ""
        if p.username:
            userinfo = f"{p.username}:****@" if p.password is not None else f"{p.username}@"
        hostport = p.hostname or ""
        if p.port:
            hostport += f":{p.port}"
        netloc = userinfo + hostport
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return url

def _mask_redis_url(url: str) -> str:
    try:
        p = urlparse(url)
        userinfo = ""
        if p.username or p.password is not None:
            userinfo = "****@"
        hostport = p.hostname or ""
        if p.port:
            hostport += f":{p.port}"
        netloc = userinfo + hostport
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return url

# Enhanced database connection debugging for Lambda
logger.info(f"🔗 DATABASE CONNECTION SETUP:")
logger.info(f"📍 Environment: AWS_LAMBDA_FUNCTION_NAME={os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'None')}")
logger.info(f"📍 AWS Execution Env: {os.getenv('AWS_EXECUTION_ENV', 'unknown')}")
logger.info(f"📍 AWS Region: {os.getenv('AWS_REGION', 'unknown')} (default={os.getenv('AWS_DEFAULT_REGION', 'unknown')})")
logger.info(f"📍 VPC ID: {os.getenv('VPC_ID', 'unknown')}")
logger.info(f"📍 Subnet IDs: {os.getenv('SUBNET_IDS', 'unknown')}")
logger.info(f"📍 Security Group: {os.getenv('SECURITY_GROUP_ID', 'unknown')}")
logger.info(f"🌐 DATABASE_URL (masked): {_mask_url_credentials(settings.DATABASE_URL)}")
masked_redis_url = _mask_redis_url(getattr(settings, 'REDIS_URL', ''))
if masked_redis_url:
    logger.info(f"🌐 REDIS_URL (masked): {masked_redis_url}")
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
        },
        "timeout": 10,  # tighter connection timeout
        "command_timeout": 15,  # tighter query timeout
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
        echo=False,  # reduce noise
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

# Lightweight preflight diagnostics (DNS + TCP + TLS) at import time
_db_preflight_ran = False

def _extract_db_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    netloc = parsed.netloc.split('@')[-1]
    host_port = netloc.rsplit(':', 1)
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) == 2 and host_port[1].isdigit() else 5432
    return host, port

def _dns_lookup(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addrs = []
    for info in infos:
        sockaddr = info[4]
        addrs.append(sockaddr[0])
    seen = set()
    unique = []
    for ip in addrs:
        if ip not in seen:
            seen.add(ip)
            unique.append(ip)
    return unique

def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    with socket.create_connection((host, port), timeout=timeout) as s:
        return True

async def _run_db_preflight(url: str) -> None:
    host, port = _extract_db_host_port(url)
    steps = []
    loop = asyncio.get_event_loop()
    # DNS
    try:
        t0 = loop.time()
        ips = await asyncio.wait_for(asyncio.to_thread(_dns_lookup, host, port), timeout=2.0)
        steps.append(("DNS", True, f"{host}->{ips} {loop.time()-t0:.2f}s"))
    except asyncio.TimeoutError:
        steps.append(("DNS", False, "timeout 2.0s"))
    except Exception as e:
        steps.append(("DNS", False, str(e)))
    # TCP
    try:
        t0 = loop.time()
        await asyncio.wait_for(asyncio.to_thread(_tcp_probe, host, port, 2.0), timeout=3.0)
        steps.append(("TCP", True, f"{host}:{port} {loop.time()-t0:.2f}s"))
    except asyncio.TimeoutError:
        steps.append(("TCP", False, "timeout 3.0s"))
    except Exception as e:
        steps.append(("TCP", False, str(e)))
    # TLS
    try:
        t0 = loop.time()
        ctx = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host=host, port=port, ssl=ctx, server_hostname=host), timeout=3.0)
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        steps.append(("TLS", True, f"handshake {loop.time()-t0:.2f}s"))
    except asyncio.TimeoutError:
        steps.append(("TLS", False, "timeout 3.0s"))
    except Exception as e:
        steps.append(("TLS", False, str(e)))
    summary = " ".join([f"{'✅' if ok else '❌'} {name}({detail})" for name, ok, detail in steps])
    logger.info(f"DB CHECKLIST: {summary}")

# Attach simple engine event hooks for clarity
try:
    if not getattr(engine, "_diag_events", False):
        @event.listens_for(engine.sync_engine, "connect")
        def _on_connect(dbapi_connection, connection_record):
            logger.info("✅ DB EVENT: CONNECT established")

        @event.listens_for(engine.sync_engine, "checkout")
        def _on_checkout(dbapi_connection, connection_record, connection_proxy):
            logger.info("✅ DB EVENT: POOL CHECKOUT")

        @event.listens_for(engine.sync_engine, "handle_error")
        def _on_error(exception_context):
            logger.error(f"❌ DB EVENT: ERROR {getattr(exception_context, 'original_exception', exception_context)}")

        engine._diag_events = True  # type: ignore[attr-defined]
except Exception:
    pass

# Lightweight preflight diagnostics (DNS + TCP) at first use
_db_preflight_ran = False

def _extract_db_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    netloc = parsed.netloc.split('@')[-1]
    host_port = netloc.rsplit(':', 1)
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) == 2 and host_port[1].isdigit() else 5432
    return host, port

def _dns_lookup(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addrs = []
    for info in infos:
        sockaddr = info[4]
        addrs.append(sockaddr[0])
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for ip in addrs:
        if ip not in seen:
            seen.add(ip)
            unique.append(ip)
    return unique

def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    with socket.create_connection((host, port), timeout=timeout) as s:
        return True

async def _run_db_preflight(url: str) -> None:
    host, port = _extract_db_host_port(url)
    logger.info(f"🧪 DB PREFLIGHT: host={host}, port={port}")
    try:
        ips = await asyncio.wait_for(asyncio.to_thread(_dns_lookup, host, port), timeout=2.0)
        logger.info(f"🧪 DB PREFLIGHT: DNS {host} -> {ips}")
    except asyncio.TimeoutError:
        logger.error("🧪 DB PREFLIGHT: DNS resolution timed out after 2.0s")
    except Exception as e:
        logger.error(f"🧪 DB PREFLIGHT: DNS error: {e}")
    try:
        ok = await asyncio.wait_for(asyncio.to_thread(_tcp_probe, host, port, 2.0), timeout=3.0)
        logger.info(f"🧪 DB PREFLIGHT: TCP connect {host}:{port} -> {ok}")
    except asyncio.TimeoutError:
        logger.error("🧪 DB PREFLIGHT: TCP connect timed out after 3.0s")
    except Exception as e:
        logger.error(f"🧪 DB PREFLIGHT: TCP error: {e}")

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