"""
Production-ready FastAPI application with consolidated middleware and monitoring.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.api.v1.api import api_router, monitoring_router
from app.core.production_middleware import ProductionMiddleware
from app.core.auth_middleware import SessionAuthenticationMiddleware
from app.monitoring.logging_config import setup_structured_logging, get_logger
from app.monitoring.metrics import metrics
import os
import asyncio

# Optional: Sentry and OpenTelemetry setup
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    OTEL_AVAILABLE = True
except Exception:
    OTEL_AVAILABLE = False

# Initialize structured logging
setup_structured_logging()
logger = get_logger("app.main")

# Initialize FastAPI app
app = FastAPI(
    title="ReFocused API",
    description="Production-ready backend API for the ReFocused productivity application",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production() else None,  # Disable docs in production
    redoc_url="/redoc" if not settings.is_production() else None,
    openapi_url="/openapi.json" if not settings.is_production() else None
)

# --- START OF DEBUG CODE FOR CORS ---
# Get the comma-separated string of origins from the environment variable
allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
# 1. Print the raw value from the environment variable
print(f"--- DEBUG PRODUCTION: CORS_ALLOWED_ORIGINS from env: '{allowed_origins_str}'")
logger.info(f"--- DEBUG PRODUCTION: CORS_ALLOWED_ORIGINS from env: '{allowed_origins_str}'")

# Parse the JSON list from environment variable
cors_origins = []
if allowed_origins_str:
    try:
        import json
        cors_origins = json.loads(allowed_origins_str)
        print(f"--- DEBUG PRODUCTION: Parsed CORS origins from JSON: {cors_origins}")
        logger.info(f"--- DEBUG PRODUCTION: Parsed CORS origins from JSON: {cors_origins}")
    except json.JSONDecodeError:
        # Fallback to comma-separated parsing
        cors_origins = [origin.strip() for origin in allowed_origins_str.split(',') if origin.strip()]
        print(f"--- DEBUG PRODUCTION: Parsed CORS origins from CSV: {cors_origins}")
        logger.info(f"--- DEBUG PRODUCTION: Parsed CORS origins from CSV: {cors_origins}")

# Always include production URLs + development + Google + environment configured origins
final_cors_origins = [
    "https://www.refocused.app",
    "https://refocused.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://accounts.google.com"
] + cors_origins + settings.CORS_ALLOWED_ORIGINS

# Remove duplicates while preserving order
final_cors_origins = list(dict.fromkeys(final_cors_origins))
# 2. Print the final list that will be used
print(f"--- DEBUG PRODUCTION: Final CORS origins list: {final_cors_origins}")
logger.info(f"--- DEBUG PRODUCTION: Final CORS origins list: {final_cors_origins}")

# CORS Configuration - must be first middleware
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

# 3. Print a confirmation that the middleware was added
print("--- DEBUG PRODUCTION: CORSMiddleware has been added to the app for App Runner.")
logger.info("--- DEBUG PRODUCTION: CORSMiddleware has been added to the app for App Runner.")
# --- END OF DEBUG CODE ---

# Session middleware for authentication
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Authentication middleware
app.add_middleware(SessionAuthenticationMiddleware)

# Consolidated production middleware (replaces multiple security/monitoring middleware)
app.add_middleware(ProductionMiddleware)

# Trusted hosts (production only) - DISABLED FOR DEBUGGING
# if settings.is_production():
#     app.add_middleware(
#         TrustedHostMiddleware,
#         allowed_hosts=getattr(settings, 'TRUSTED_HOSTS', ["*"])
#     )

# Compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API routers
app.include_router(api_router, prefix="/api/v1")

# Include monitoring routes at root level (no prefix)
app.include_router(monitoring_router)

# Root-level auth refresh alias for clients calling /auth/refresh
from app.api.v1.endpoints.auth import enhanced_refresh_token as _refresh_handler
app.add_api_route("/auth/refresh", _refresh_handler, methods=["POST"], tags=["auth"])  # delegates to /api/v1/auth/refresh handler

# Add mood route aliases (needed in production until frontend is updated)
from app.routers import mood as mood_router
app.include_router(mood_router.router, prefix="/mood", tags=["mood-alias-prod"])
logger.info("✅ Mood route aliases added: /mood/* -> /api/v1/mood/* (production compatible)")

def _setup_sentry_and_tracing():
    if settings.SENTRY_DSN:
        try:
            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
                integrations=[FastApiIntegration()],
                environment=settings.APP_ENV,
                release="1.0.0",
            )
            logger.info("✅ Sentry initialized")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Sentry: {e}")

    if OTEL_AVAILABLE and settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        try:
            resource = Resource(attributes={
                "service.name": settings.OTEL_SERVICE_NAME,
                "deployment.environment": settings.APP_ENV,
            })
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            logger.info("✅ OpenTelemetry tracing initialized")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize OpenTelemetry: {e}")

async def _run_db_migrations_if_enabled():
    if settings.RUN_DB_MIGRATIONS_ON_STARTUP:
        try:
            logger.info("🗂️ Creating database tables...")
            from app.db.models import Base
            from app.db.database import engine
            # Create all tables directly from models
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables created")
        except Exception as e:
            logger.error(f"❌ Failed to create tables: {e}")
            raise

@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("🚀 ReFocused API starting up...")
    
    # Initialize monitoring
    metrics.set_health_status(True)

    # Error tracking & tracing
    _setup_sentry_and_tracing()
    
    # Run DB migrations and ping unless running under pytest (avoid event loop contention)
    import os as _os
    if not (_os.getenv("PYTEST_CURRENT_TEST") or _os.getenv("DISABLE_DB_STARTUP") == "1"):
        try:
            await _run_db_migrations_if_enabled()
            from app.db.database import async_session
            from sqlalchemy import text
            async with async_session() as db:
                await db.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {str(e)}")
            metrics.set_health_status(False)
            raise
    
    # Log configuration
    logger.info(f"🏃 Running in {settings.APP_ENV} mode")
    logger.info(f"🔒 Rate limiting: {'enabled' if settings.RATE_LIMIT_ENABLED else 'disabled'}")
    logger.info(f"🌐 CORS origins: {settings.CORS_ALLOWED_ORIGINS}")
    
    logger.info("🎉 ReFocused API startup complete!")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("📤 ReFocused API shutting down...")
    metrics.set_health_status(False)

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "ReFocused API",
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
        "app.main_production:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production(),
        log_level="info" if settings.is_production() else "debug"
    ) 