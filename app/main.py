"""
Main entry point for the ReFocused API.
"""

import logging
import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.api.v1.api import api_router, monitoring_router
from app.core.production_middleware import ProductionMiddleware
from app.core.auth_middleware import SessionAuthenticationMiddleware
from app.monitoring.logging_config import setup_structured_logging, get_logger
from app.monitoring.metrics import metrics
from app.routers import mood as mood_router
from app.api.v1.endpoints.auth import enhanced_refresh_token as _refresh_handler

setup_structured_logging()
logger = get_logger("app.main")

app = FastAPI(
    title="ReFocused API",
    description="Backend API for the ReFocused productivity application",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production() else None,
    redoc_url="/redoc" if not settings.is_production() else None,
    openapi_url="/openapi.json" if not settings.is_production() else None
)

# --- CORS Configuration ---
def get_cors_origins():
    """Parse CORS origins from environment or settings."""
    origins = settings.CORS_ALLOWED_ORIGINS.copy()
    
    # Check for additional origins in environment variable
    env_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if env_origins:
        try:
            parsed = json.loads(env_origins)
            if isinstance(parsed, list):
                origins.extend(parsed)
        except json.JSONDecodeError:
            origins.extend([o.strip() for o in env_origins.split(',') if o.strip()])
            
    # Add default known origins
    defaults = [
        "https://www.refocused.app",
        "https://refocused.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://accounts.google.com"
    ]
    origins.extend(defaults)
    
    return list(dict.fromkeys(origins))  # Deduplicate

final_cors_origins = get_cors_origins()
logger.info(f"CORS origins configured: {len(final_cors_origins)} allowed domains")

app.add_middleware(
    CORSMiddleware,
    allow_origins=final_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "*",
        "Authorization",
        "Content-Type",
        "X-Refresh-Token",
        settings.CSRF_HEADER_NAME,
        "X-App-Env",
        "X-Client-Version",
        "X-User-Timezone",
    ],
    expose_headers=["X-Correlation-ID", "X-Response-Time", "Set-Cookie"]
)

# --- Middleware Registration ---
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(SessionAuthenticationMiddleware)
app.add_middleware(ProductionMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# --- Router Registration ---
app.include_router(api_router, prefix="/api/v1")
app.include_router(monitoring_router)
app.include_router(mood_router.router, prefix="/api/mood", tags=["mood-alias"])

# Direct route registration for auth refresh
app.add_api_route("/auth/refresh", _refresh_handler, methods=["POST"], tags=["auth"])
app.add_api_route("/api/v1/auth/refresh/", _refresh_handler, methods=["POST"], tags=["auth"])
app.add_api_route("/auth/refresh/", _refresh_handler, methods=["POST"], tags=["auth"])

async def _run_db_migrations_if_enabled():
    if settings.RUN_DB_MIGRATIONS_ON_STARTUP:
        try:
            logger.info("Initializing database schema...")
            from app.db.models import Base
            from app.db.database import engine
            
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database schema initialized.")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")
    
    metrics.set_health_status(True)

    # Check database connection
    import os as _os
    if not (_os.getenv("PYTEST_CURRENT_TEST") or _os.getenv("DISABLE_DB_STARTUP") == "1"):
        try:
            await _run_db_migrations_if_enabled()
            from app.db.database import async_session
            from sqlalchemy import text
            async with async_session() as db:
                await db.execute(text("SELECT 1"))
            logger.info("Database connection established.")
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            metrics.set_health_status(False)
            raise

    # Check Redis connection
    try:
        from app.caching.redis_cache import cache
        if cache.enabled:
            if await cache.ping():
                logger.info("Redis connection established.")
            else:
                logger.warning("Redis ping failed, caching may be degraded.")
        else:
            logger.info("Redis disabled via configuration.")
    except Exception as e:
        logger.warning(f"Redis connection issue: {e}")

    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info("Startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down...")
    metrics.set_health_status(False)

@app.get("/")
async def root():
    return {
        "name": "ReFocused API",
        "version": "1.0.0",
        "status": "active",
        "environment": settings.APP_ENV,
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "api": "/api/v1",
            "docs": "/docs" if not settings.is_production() else "disabled"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production(),
        log_level="info" if settings.is_production() else "debug"
    )
