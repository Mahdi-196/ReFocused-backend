from fastapi import FastAPI, Request, Response, Depends, HTTPException
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

from app.core.config import settings
from app.api.v1.api import api_router, monitoring_router

from app.core.security_middleware import (
    SecurityMiddleware,
    RequestValidationMiddleware,
    SQLInjectionProtectionMiddleware,
    UserDataIsolationMiddleware
)
from app.core.security_monitor import SecurityMonitor
from app.db.database import get_db, async_session
from app.core.auth import get_current_user
from app.db.models import User

# Basic logging setup
logging.basicConfig(
    level=settings.SECURITY_LOG_LEVEL,
    format=settings.SECURITY_LOG_FORMAT,
    filename=settings.SECURITY_LOG_PATH
)
logger = logging.getLogger("app")

# Rate limiting now handled by UnifiedSecurityMiddleware


# Initialize FastAPI app
app = FastAPI(
    title="ReFocused API",
    description="Backend API for the ReFocused productivity application",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# HTTPS will be handled by AWS infrastructure (ALB/CloudFront)

# CORS must be the FIRST middleware - Enhanced for cookies and auth
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://accounts.google.com",  # Allow Google OAuth origin
    ],
    allow_credentials=True,  # Essential for cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "*",
        "Authorization",
        "Content-Type", 
        "X-Refresh-Token",
        "X-Requested-With",
        "Cookie"
    ],
    expose_headers=[
        "Set-Cookie",
        "X-Process-Time",
        "X-API-Version"
    ]
)

# Add authentication middleware (after CORS, before other middleware)
from app.core.auth_middleware import AuthenticationMiddleware, SessionAuthenticationMiddleware
app.add_middleware(SessionAuthenticationMiddleware)  # For automatic refresh

# Add unified security middleware after auth
from app.core.unified_middleware import UnifiedSecurityMiddleware
app.add_middleware(UnifiedSecurityMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"] if not settings.is_production() else settings.TRUSTED_HOSTS)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Add compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API router
app.include_router(api_router, prefix="/api/v1")
app.include_router(monitoring_router)  # Mount monitoring at root level

# Google OAuth COOP middleware - Fixed to properly handle OAuth flows
@app.middleware("http")
async def google_oauth_coop_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # Always allow popups for OAuth - this is required for Google OAuth to work
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
    
    return response

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    request.state.start_time = start_time
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Security monitoring middleware - DISABLED for development performance
@app.middleware("http")
async def security_monitoring(request: Request, call_next):
    # Skip ALL security monitoring in development to improve performance
    if settings.is_development():
        return await call_next(request)
    
    # Skip security monitoring for auth endpoints, health checks, and CORS preflight requests
    if any(path in str(request.url.path) for path in ["/auth/", "/health", "/docs", "/redoc", "/openapi.json"]) or request.method == "OPTIONS":
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

# Debug endpoint for troubleshooting
@app.get("/debug/headers")
async def debug_headers(request: Request):
    """Debug endpoint to check what headers are being received"""
    return {
        "headers": dict(request.headers),
        "method": request.method,
        "url": str(request.url),
        "client": request.client.host if request.client else None
    }

# Debug mock date endpoints removed - using real dates only

# Debug auth endpoint
@app.get("/debug/auth")
async def debug_auth(request: Request, db: AsyncSession = Depends(get_db)):
    """Debug endpoint to test authentication"""
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
    if origin in ["http://localhost:3000", "http://127.0.0.1:3000", "https://accounts.google.com"]:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
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
    logger.info(f"🔒 Security logging: {'enabled' if settings.SECURITY_LOG_ENABLED else 'disabled'}")
    logger.info(f"🌐 CORS origins: {settings.CORS_ALLOWED_ORIGINS}")
    
    # Start background mood cleanup task
    try:
        import asyncio
        from app.tasks.mood_cleanup import MoodCleanupScheduler
        
        # Start the cleanup scheduler in the background
        asyncio.create_task(MoodCleanupScheduler.schedule_daily_cleanup())
        logger.info("✅ Mood cleanup scheduler started")
        
    except Exception as e:
        logger.warning(f"⚠️ Failed to start mood cleanup scheduler: {str(e)}")
    
    logger.info("🎉 ReFocused API startup complete!")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown - Security features terminated")
    
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

# Catch-all for missing API prefix - redirect to correct endpoints
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