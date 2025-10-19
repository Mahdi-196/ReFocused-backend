from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import time
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging
from datetime import datetime
from fastapi.responses import JSONResponse
import json
import traceback

from app.core.config import settings
from app.api.v1.api import api_router, monitoring_router

from app.core.security_middleware import (
    SecurityMiddleware,
    RequestValidationMiddleware,
    SQLInjectionProtectionMiddleware,
    UserDataIsolationMiddleware
)
from app.core.security_monitor import SecurityMonitor
from app.core.streak_middleware import StreakTrackingMiddleware
from app.db.database import get_db, async_session
from app.core.auth import get_current_user
from app.db.models import User

# Enhanced logging setup for Lambda/CloudWatch
import sys
import structlog

# Configure logging for CloudWatch (stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)  # CloudWatch captures stdout
    ],
    force=True  # Override any existing logging config
)

# Create loggers for different components
logger = logging.getLogger("refocused.app")
mangum_logger = logging.getLogger("mangum")
db_logger = logging.getLogger("refocused.db")
auth_logger = logging.getLogger("refocused.auth")

# Set log levels
logger.setLevel(logging.INFO)
mangum_logger.setLevel(logging.INFO)
db_logger.setLevel(logging.INFO)
auth_logger.setLevel(logging.INFO)

logger.info("🚀 ReFocused API starting up...")

# Rate limiting now handled by UnifiedSecurityMiddleware


# Initialize FastAPI app
logger.info("🔧 Creating FastAPI application instance")
app = FastAPI(
    title="ReFocused API",
    description="Backend API for the ReFocused productivity application",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
logger.info("✅ FastAPI application created successfully")

# HTTPS will be handled by AWS infrastructure (ALB/CloudFront)

# --- START OF DEBUG CODE FOR CORS ---
import os

# Get the comma-separated string of origins from the environment variable
allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
# 1. Print the raw value from the environment variable
print(f"--- DEBUG: CORS_ALLOWED_ORIGINS from env: '{allowed_origins_str}'")
logger.info(f"--- DEBUG: CORS_ALLOWED_ORIGINS from env: '{allowed_origins_str}'")

# Parse the JSON list from environment variable
cors_origins = []
if allowed_origins_str:
    try:
        import json
        cors_origins = json.loads(allowed_origins_str)
        print(f"--- DEBUG: Parsed CORS origins from JSON: {cors_origins}")
        logger.info(f"--- DEBUG: Parsed CORS origins from JSON: {cors_origins}")
    except json.JSONDecodeError:
        # Fallback to comma-separated parsing
        cors_origins = [origin.strip() for origin in allowed_origins_str.split(',') if origin.strip()]
        print(f"--- DEBUG: Parsed CORS origins from CSV: {cors_origins}")
        logger.info(f"--- DEBUG: Parsed CORS origins from CSV: {cors_origins}")

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
print(f"--- DEBUG: Final CORS origins list: {final_cors_origins}")
logger.info(f"--- DEBUG: Final CORS origins list: {final_cors_origins}")

# Add CORS middleware for App Runner (not API Gateway!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=final_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["Accept", "Accept-Language", "Content-Language", "Content-Type", "Authorization", "X-Requested-With", "X-CSRFToken", "X-CSRF-Token", "Cache-Control", "Pragma", "Origin", "Referer", "User-Agent", "X-Refresh-Token", "X-App-Env", "X-Client-Version", "X-User-Timezone", "Cookie"],
)

# 3. Print a confirmation that the middleware was added
print("--- DEBUG: CORSMiddleware has been added to the app for App Runner.")
logger.info("--- DEBUG: CORSMiddleware has been added to the app for App Runner.")
# --- END OF DEBUG CODE ---

# Production-optimized middleware - minimal logging
if settings.is_development():
    class DebugMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            start_time = time.time()
            logger.info(f"🔄 {request.method} {request.url.path}")
            
            try:
                response = await call_next(request)
                process_time = time.time() - start_time
                logger.info(f"✅ {request.method} {request.url.path} -> {response.status_code} ({process_time:.3f}s)")
                return response
            except Exception as e:
                process_time = time.time() - start_time
                logger.error(f"❌ {request.method} {request.url.path} -> ERROR ({process_time:.3f}s): {str(e)}")
                raise

    logger.info("🔍 Adding debug middleware (development mode)")
    app.add_middleware(DebugMiddleware)
    logger.info("✅ Debug middleware added")
else:
    logger.info("🏭 Production mode - debug middleware disabled")

# Add authentication middleware (after CORS, before other middleware)
logger.info("🔐 Setting up authentication middleware")
try:
    from app.core.auth_middleware import AuthenticationMiddleware, SessionAuthenticationMiddleware
    app.add_middleware(SessionAuthenticationMiddleware)  # For automatic refresh
    logger.info("✅ Authentication middleware configured")
except Exception as e:
    logger.error(f"❌ Failed to setup auth middleware: {str(e)}")
    raise

# Add unified security middleware after auth
logger.info("🛡️ Setting up security middleware")
try:
    from app.core.unified_middleware import UnifiedSecurityMiddleware
    app.add_middleware(UnifiedSecurityMiddleware)
    logger.info("✅ Security middleware configured")
except Exception as e:
    logger.error(f"❌ Failed to setup security middleware: {str(e)}")
    raise

# Add streak tracking middleware
logger.info("📈 Setting up streak tracking middleware")
try:
    app.add_middleware(StreakTrackingMiddleware)
    logger.info("✅ Streak tracking middleware configured")
except Exception as e:
    logger.error(f"❌ Failed to setup streak middleware: {str(e)}")
    raise

logger.info("🔧 Setting up basic middleware (TrustedHost, Session, GZip)")
try:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"] if not settings.is_production() else settings.TRUSTED_HOSTS)
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    logger.info("✅ Basic middleware configured successfully")
except Exception as e:
    logger.error(f"❌ Failed to setup basic middleware: {str(e)}")
    raise

# Include API router
logger.info("🛣️ Including API routers")
try:
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(monitoring_router)  # Mount monitoring at root level
    logger.info("✅ API routers included successfully")
    
    if settings.is_development():
        # Log all registered routes for debugging 405 errors
        logger.info("🔍 Logging registered routes for debugging:")
        route_count = 0
        
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                route_count += 1
                methods_str = ', '.join(sorted(route.methods)) if route.methods else 'Unknown'
                logger.info(f"  📍 {methods_str:<20} {route.path}")
        
        logger.info(f"🔍 Total registered routes: {route_count}")
    else:
        # Production: only log route count
        route_count = sum(1 for route in app.routes if hasattr(route, 'path') and hasattr(route, 'methods'))
        logger.info(f"📍 Registered {route_count} API routes")
    
except Exception as e:
    logger.error(f"❌ Failed to include API routers: {str(e)}")
    raise

# Email subscription endpoints removed; using AWS API Gateway + Lambda directly

# Root-level auth refresh alias for clients calling /auth/refresh
from app.api.v1.endpoints.auth import enhanced_refresh_token as _refresh_handler
app.add_api_route("/auth/refresh", _refresh_handler, methods=["POST"], tags=["auth"])  # delegates to /api/v1/auth/refresh handler

# Add mood route aliases (needed in production until frontend is updated)
from app.routers import mood as mood_router
app.include_router(mood_router.router, prefix="/mood", tags=["mood-alias-prod"])
logger.info("✅ Mood route aliases added: /mood/* -> /api/v1/mood/* (production compatible)")

# Production: Skip route aliases (frontend should use /api/v1)
if settings.is_development():
    # TEMPORARY: Add route aliases for frontend compatibility (missing /api/v1 prefix)
    logger.info("🔧 Adding temporary route aliases for frontend compatibility")
    
    # Add auth route aliases
    from app.api.v1.endpoints import auth
    app.include_router(auth.router, prefix="/auth", tags=["auth-alias"])
    logger.info("✅ Auth route aliases added: /auth/* -> /api/v1/auth/*")
    
    # Add AI route aliases
    from app.api.v1.endpoints import ai
    app.include_router(ai.router, prefix="/ai", tags=["ai-alias"])
    logger.info("✅ AI route aliases added: /ai/* -> /api/v1/ai/*")

    logger.info("⚠️ IMPORTANT: Route aliases are temporary - update frontend to use /api/v1 prefix")
else:
    logger.info("🏭 Production mode - route aliases disabled (use /api/v1 prefix)")

# Explicit OPTIONS handler to fix Lambda Function URL CORS override
@app.options("/{path:path}")
async def options_handler(request: Request):
    """Handle all OPTIONS requests with proper CORS headers"""
    origin = request.headers.get("origin")
    
    # Always include production URLs + development + Google + environment configured origins
    allowed_origins = [
        "https://www.refocused.app",
        "https://refocused.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://accounts.google.com"
    ] + settings.CORS_ALLOWED_ORIGINS
    
    # Remove duplicates while preserving order
    allowed_origins = list(dict.fromkeys(allowed_origins))
    
    response = Response(status_code=200)
    
    # Always set CORS headers for production and development
    if origin in allowed_origins or origin is None:
        response.headers["Access-Control-Allow-Origin"] = origin or "https://www.refocused.app"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, X-CSRFToken, X-CSRF-Token, Cache-Control, Pragma, Origin, Referer, User-Agent, X-Refresh-Token, X-App-Env, X-Client-Version, X-User-Timezone, Cookie"
        response.headers["Access-Control-Max-Age"] = "86400"  # Cache for 24 hours
        
        # Log the CORS response for debugging
        logger.info(f"🔍 OPTIONS request from {origin}")
        logger.info(f"✅ Responding with CORS headers - Origin allowed")
    else:
        # Even for unknown origins, provide basic CORS to prevent failures
        response.headers["Access-Control-Allow-Origin"] = "https://www.refocused.app"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, X-CSRFToken, X-CSRF-Token, Cache-Control, Pragma, Origin, Referer, User-Agent, X-Refresh-Token, X-App-Env, X-Client-Version, X-User-Timezone, Cookie"
        response.headers["Access-Control-Max-Age"] = "86400"
        logger.warning(f"❌ OPTIONS request from unknown origin: {origin} - Using default CORS")
    
    return response

# CORS now properly configured for App Runner deployment
logger.info("🌐 CORS middleware configured for App Runner")

# Add final startup confirmation
logger.info("🎉 FastAPI application startup completed successfully")
logger.info("📡 Ready to handle requests via API Gateway")

# Enhanced CORS middleware - Ensures ALL responses have proper CORS headers
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    
    # Always include production URLs + development + Google + environment configured origins
    allowed_origins = [
        "https://www.refocused.app",
        "https://refocused.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://accounts.google.com"
    ] + settings.CORS_ALLOWED_ORIGINS

    # Remove duplicates while preserving order
    allowed_origins = list(dict.fromkeys(allowed_origins))
    
    response = await call_next(request)
    
    # Always set CORS headers - critical for fixing the authentication issues
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "https://www.refocused.app"
    
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, X-CSRFToken, X-CSRF-Token, Cache-Control, Pragma, Origin, Referer, User-Agent, X-Refresh-Token, X-App-Env, X-Client-Version, X-User-Timezone, Cookie"
    response.headers["Access-Control-Max-Age"] = "86400"
    
    return response

# Google OAuth COOP middleware - Fixed to properly handle OAuth flows
@app.middleware("http")
async def google_oauth_coop_middleware(request: Request, call_next):
    response = await call_next(request)

    # For Google OAuth endpoints, use unsafe-none to allow window.postMessage
    # For other endpoints, use same-origin-allow-popups for better security
    if "/auth/google" in request.url.path or "/google" in request.url.path:
        response.headers["Cross-Origin-Opener-Policy"] = "unsafe-none"
        logger.info(f"🔓 COOP set to unsafe-none for Google OAuth: {request.url.path}")
    else:
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"

    response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
    # Echo observability headers for debugging (non-sensitive)
    app_env = request.headers.get("x-app-env")
    client_version = request.headers.get("x-client-version")
    user_tz = request.headers.get("x-user-timezone")
    if app_env:
        response.headers["X-App-Env"] = app_env
    if client_version:
        response.headers["X-Client-Version"] = client_version
    if user_tz:
        response.headers["X-User-Timezone"] = user_tz
    
    return response

# Production-optimized request middleware
@app.middleware("http")
async def enhanced_request_middleware(request: Request, call_next):
    start_time = time.time()
    request.state.start_time = start_time
    
    # Minimal logging in production
    if settings.is_development():
        logger.info(f"🔄 {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Add timing header
        response.headers["X-Process-Time"] = str(process_time)
        
        # Ensure caches vary on Origin for CORS
        response.headers["Vary"] = ", ".join(filter(None, [response.headers.get("Vary"), "Origin"]))
        
        # Pass a CSRF header name so the client knows which header to use
        if settings.CSRF_ENABLED:
            response.headers["X-CSRF-Header-Name"] = settings.CSRF_HEADER_NAME
        
        # Log only errors in production    
        if settings.is_development():
            logger.info(f"✅ {request.method} {request.url.path} -> {response.status_code} ({process_time:.3f}s)")
        elif response.status_code >= 400:
            logger.warning(f"⚠️ {request.method} {request.url.path} -> {response.status_code} ({process_time:.3f}s)")
            
        return response
        
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"❌ {request.method} {request.url.path} -> ERROR ({process_time:.3f}s): {str(e)}")
        raise

# Security monitoring middleware - only in production
if not settings.is_development():
    @app.middleware("http")
    async def security_monitoring(request: Request, call_next):
        # Skip security monitoring for health checks and CORS preflight requests
        if any(path in str(request.url.path) for path in ["/health", "/docs", "/redoc", "/openapi.json"]) or request.method == "OPTIONS":
            return await call_next(request)
        
        try:
            # Process the request first, then monitor
            response = await call_next(request)
            
            # Only monitor after successful request processing
            async with async_session() as db:
                security_monitor = SecurityMonitor(db)
                
                # Try to get current user, but don't fail if not authenticated
                user_id = None
                try:
                    auth_header = request.headers.get("Authorization")
                    if auth_header and auth_header.startswith("Bearer "):
                        token = auth_header.split(" ")[1]
                        from app.core.auth import get_current_user_from_token
                        user = await get_current_user_from_token(token, db)
                        user_id = user.id if user else None
                except Exception:
                    # User not authenticated or token invalid - that's fine
                    pass
                
                # Monitor the request without failing
                try:
                    await security_monitor.monitor_request(request, user_id)
                except Exception as e:
                    logger.warning(f"Security monitoring warning: {str(e)}")
            
            return response
                
        except Exception as e:
            logger.error(f"Security monitoring error: {str(e)}")
            return await call_next(request)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ReFocused API",
        "timestamp": datetime.utcnow().isoformat()
    }

# Statistics health check endpoint
@app.get("/health/statistics")
async def statistics_health_check():
    """Simple health check for statistics functionality"""
    try:
        from app.schemas.statistics import FocusTimeUpdate, StatisticsResponse
        
        # Test schema creation
        test_request = FocusTimeUpdate(minutes=1)
        test_response = StatisticsResponse(focusTime=0, sessions=0, tasksDone=0)
        
        return {
            "status": "healthy",
            "message": "Statistics schemas working",
            "uses_minutes": True,
            "test_request": test_request.model_dump(),
            "test_response": test_response.model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Statistics error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }

# Debug endpoints disabled in production for security
if settings.is_development():
    @app.get("/debug/headers")
    async def debug_headers(request: Request):
        return {
            "headers": dict(request.headers),
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else None
        }

# Debug endpoints - development only
if settings.is_development():
    @app.get("/debug/redis")
    async def debug_redis():
        """Debug Redis connection and test basic operations"""
        from app.caching.redis_cache import cache
        
        logger.info("🔍 Debug Redis endpoint called")
        
        debug_info = await cache.debug_connection()
        test_results = await cache.test_basic_operations()
        
        result = {
            "connection_info": debug_info,
            "operation_tests": test_results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"🔍 Redis debug results: {result}")
        return result
    
    @app.get("/debug/routes")
    async def debug_routes():
        """List all registered routes to help identify routing issues"""
        
        logger.info("🔍 Debug routes endpoint called")
        
        routes_info = []
        for route in app.routes:
            if hasattr(route, 'path'):
                route_info = {
                    "path": route.path,
                    "methods": list(route.methods) if hasattr(route, 'methods') else ['Unknown'],
                    "name": route.name if hasattr(route, 'name') else 'Unknown'
                }
                routes_info.append(route_info)
        
        result = {
            "total_routes": len(routes_info),
            "routes": sorted(routes_info, key=lambda x: x['path']),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"🔍 Found {len(routes_info)} routes")
        return result

# Always available debug endpoints for production troubleshooting

@app.get("/debug/env")
async def debug_environment():
    """Show sanitized environment information for debugging"""
    
    logger.info("🔍 Debug environment endpoint called")
    
    # Sanitize sensitive environment variables
    env_info = {
        "DATABASE_URL": "***SET***" if hasattr(settings, 'DATABASE_URL') and settings.DATABASE_URL else "NOT_SET",
        "REDIS_URL": "***SET***" if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL else "NOT_SET", 
        "SECRET_KEY": "***SET***" if hasattr(settings, 'SECRET_KEY') and settings.SECRET_KEY else "NOT_SET",
        "APP_ENV": getattr(settings, 'APP_ENV', 'NOT_SET'),
        "DEBUG": getattr(settings, 'DEBUG', False),
        "CORS_ORIGINS": getattr(settings, 'CORS_ORIGINS', []),
        "API_V1_STR": getattr(settings, 'API_V1_STR', '/api/v1'),
    }
    
    # Add network/Lambda information
    import os
    import socket
    
    network_info = {}
    try:
        network_info["hostname"] = socket.gethostname()
        network_info["lambda_function_name"] = os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'NOT_LAMBDA')
        network_info["lambda_region"] = os.getenv('AWS_REGION', 'NOT_SET')
        network_info["vpc_id"] = os.getenv('VPC_ID', 'NOT_SET')  # If you set this
        
        # Try to get security groups from EC2 metadata (if available)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=1.0) as client:
                # Try to get EC2/Lambda metadata
                response = await client.get('http://169.254.169.254/latest/meta-data/security-groups')
                network_info["security_groups"] = response.text.split('\n') if response.status_code == 200 else "NOT_AVAILABLE"
        except:
            network_info["security_groups"] = "METADATA_UNAVAILABLE"
            
    except Exception as e:
        network_info["error"] = str(e)
    
    result = {
        "environment": env_info,
        "network": network_info,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info("🔍 Environment debug info collected")
    return result

if settings.is_development():
    @app.get("/debug/auth")
    async def debug_auth(request: Request, db: AsyncSession = Depends(get_db)):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return {"error": "No Authorization header found", "headers": dict(request.headers)}
        if not auth_header.startswith("Bearer "):
            return {"error": "Authorization header doesn't start with 'Bearer '", "auth_header": auth_header}
        token = auth_header.split(" ")[1]
        try:
            from app.core.auth import get_current_user_from_token
            user = await get_current_user_from_token(token, db)
            return {"success": True, "user_id": user.id, "user_email": user.email}
        except Exception as e:
            return {"error": str(e), "token_preview": token[:20] + "..." if len(token) > 20 else token}

# Security metrics endpoint
@app.get("/security/metrics")
async def get_security_metrics(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user)  # Require authentication
):
    security_monitor = SecurityMonitor(db)
    return security_monitor.get_security_metrics()

# Security alerts endpoint
@app.get("/security/alerts")
async def get_security_alerts(
    resolved: bool = False,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user)  # Require authentication
):
    security_monitor = SecurityMonitor(db)
    return security_monitor.get_security_alerts(resolved)

# Critical debugging endpoints for Lambda deployment issues
@app.get("/api/v1/auth/cookie-support")
async def check_cookie_support(request: Request):
    """Critical endpoint that was failing - now with comprehensive logging"""
    auth_logger.info("🍪 Starting cookie-support check")
    try:
        auth_logger.info("✅ Cookie support check completed successfully")
        return {
            "cookie_support": True,
            "message": "ReFocused API supports cookies",
            "timestamp": datetime.utcnow().isoformat(),
            "user_agent": request.headers.get("user-agent", "unknown"),
            "origin": request.headers.get("origin", "unknown")
        }
    except Exception as e:
        auth_logger.error(f"❌ Cookie support check failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cookie support check failed: {str(e)}")

@app.get("/debug/db-test")
async def test_database_connection():
    """Test database connectivity - the most likely cause of Lambda failures"""
    db_logger.info("🗄️ Testing database connection")
    try:
        # Test database connection
        db_logger.info("📡 Attempting to create database session")
        async with async_session() as db:
            db_logger.info("✅ Database session created successfully")
            
            # Simple query test
            db_logger.info("🔍 Executing test query")
            result = await db.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            db_logger.info(f"✅ Database query successful, result: {test_value}")
            
            return {
                "status": "success",
                "message": "Database connection working",
                "test_query_result": test_value,
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        db_logger.error(f"❌ Database connection failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Database connection failed: {str(e)}",
            "error_type": str(type(e).__name__),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/debug/redis-test")
async def test_redis_connection():
    """Test Redis/ElastiCache connectivity"""
    logger.info("🔴 Testing Redis connection")
    try:
        from app.caching.redis_cache import cache
        logger.info("📡 Attempting Redis connection")
        
        if cache.enabled:
            # Test Redis connection
            await cache.ping()
            logger.info("✅ Redis connection successful")
            return {
                "status": "success",
                "message": "Redis connection working",
                "cache_enabled": True,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            logger.info("ℹ️ Redis cache is disabled")
            return {
                "status": "disabled",
                "message": "Redis cache is disabled",
                "cache_enabled": False,
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Redis connection failed: {str(e)}",
            "error_type": str(type(e).__name__),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/debug/lambda-env")
async def debug_lambda_environment():
    """Debug Lambda environment and configuration"""
    logger.info("🐍 Debugging Lambda environment")
    try:
        import os
        return {
            "status": "success",
            "environment": {
                "DATABASE_URL": os.getenv("DATABASE_URL", "not_set")[:20] + "..." if os.getenv("DATABASE_URL") else "not_set",
                "REDIS_URL": os.getenv("REDIS_URL", "not_set")[:20] + "..." if os.getenv("REDIS_URL") else "not_set",
                "SECRET_KEY": "***SET***" if os.getenv("SECRET_KEY") else "not_set",
                "APP_ENV": os.getenv("APP_ENV", "not_set"),
                "AWS_REGION": os.getenv("AWS_REGION", "not_set"),
                "AWS_LAMBDA_FUNCTION_NAME": os.getenv("AWS_LAMBDA_FUNCTION_NAME", "not_set")
            },
            "python_version": sys.version,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Environment debug failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Environment debug failed: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the full error with traceback
    logger.error(f"Global exception: {str(exc)}", exc_info=True)
    
    # Create error response with more details
    error_response = {
        "detail": "An internal server error occurred",
        "error": str(exc),  # Include the error message
        "type": exc.__class__.__name__  # Include the error type
    }
    
    # In development, include more debugging info
    if settings.is_development():
        error_response.update({
            "traceback": str(exc.__traceback__) if hasattr(exc, '__traceback__') else None,
            "path": str(request.url.path),
            "method": request.method
        })
    
    # Create response with CORS headers
    response = JSONResponse(status_code=500, content=error_response)
    
    # Add CORS headers to error responses
    origin = request.headers.get("origin")
    allowed_origins = settings.CORS_ALLOWED_ORIGINS + ["https://accounts.google.com"]
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, X-CSRFToken, X-CSRF-Token, Cache-Control, Pragma, Origin, Referer, User-Agent, X-Refresh-Token, X-App-Env, X-Client-Version, X-User-Timezone, Cookie"
    
    return response

# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger.info("🚀 ReFocused API starting up...")
    
    # Test database connection
    try:
        from app.db.database import async_session
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        raise
    
    # Load environment configuration
    logger.info(f"🏃 Running in {settings.APP_ENV} mode")
    
    # Only start schedulers in production
    if not settings.is_development():
        # Start content scheduler (daily and weekly)
        try:
            from app.core.scheduler import content_scheduler
            content_scheduler.start_scheduler()
            logger.info("✅ Content scheduler started")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start content scheduler: {str(e)}")
        
        # Start background mood cleanup task
        try:
            import asyncio
            from app.tasks.mood_cleanup import MoodCleanupScheduler
            asyncio.create_task(MoodCleanupScheduler.schedule_daily_cleanup())
            logger.info("✅ Mood cleanup scheduler started")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start mood cleanup scheduler: {str(e)}")
    
    logger.info("🎉 ReFocused API startup complete!")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Application shutdown - Security features terminated")
    
    # Stop content scheduler
    try:
        from app.core.scheduler import content_scheduler
        content_scheduler.stop_scheduler()
        logger.info("✅ Content scheduler stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping content scheduler: {str(e)}")
    
    # Streak scheduler cleanup removed - module doesn't exist

@app.get("/")
async def root():
    return {
        "message": "ReFocused API is running",
        "version": "1.0.0",
        "status": "active",
        "auth_endpoints": {
            "register": "/api/v1/auth/register",
            "login": "/api/v1/auth/token", 
            "logout": "/api/v1/auth/logout",
            "profile": "/api/v1/auth/me"
        }
    }

# Catch-all for missing API prefix - development only
if settings.is_development():
    @app.get("/goals")
    async def redirect_goals():
        raise HTTPException(
            status_code=404,
            detail="Endpoint not found. Did you mean '/api/v1/goals'? Make sure your frontend API base URL includes '/api/v1'"
        )
    
    @app.get("/habits")
    async def redirect_habits():
        raise HTTPException(
            status_code=404,
            detail="Endpoint not found. Did you mean '/api/v1/habits'? Make sure your frontend API base URL includes '/api/v1'"
        )
    
    @app.get("/auth/{path:path}")
    async def redirect_auth(path: str):
        raise HTTPException(
            status_code=404,
            detail=f"Endpoint not found. Did you mean '/api/v1/auth/{path}'? Make sure your frontend API base URL includes '/api/v1'"
        ) 