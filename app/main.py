from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import time
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from datetime import datetime
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.api.v1.api import api_router
from app.core.security_middleware import (
    SecurityMiddleware,
    RequestValidationMiddleware,
    SQLInjectionProtectionMiddleware,
    UserDataIsolationMiddleware
)
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.transaction import TransactionMiddleware
from app.core.security_monitor import SecurityMonitor
from app.db.database import get_db, async_session
from app.core.auth import get_current_user
from app.utils.logging import setup_logging, get_logger
from app.core.error_handling import register_exception_handlers

# Configure structured logging
setup_logging(level=logging.INFO if settings.DEBUG else logging.WARNING)
logger = get_logger("app")

# Simple rate limiting
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, timeframe_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.timeframe = timeframe_seconds
        self.request_counts = {}
        
    async def dispatch(self, request: Request, call_next):
        # Skip in dev mode
        if settings.is_development() and not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)
            
        client_ip = request.client.host
        current_time = time.time()
        
        # Clean up old requests
        if client_ip in self.request_counts:
            self.request_counts[client_ip] = [
                timestamp for timestamp in self.request_counts[client_ip]
                if current_time - timestamp < self.timeframe
            ]
            
            # Check rate limit
            if len(self.request_counts[client_ip]) >= self.max_requests:
                return Response(
                    content="Rate limit exceeded. Please try again later.",
                    status_code=429
                )
                
            # Add current request
            self.request_counts[client_ip].append(current_time)
        else:
            self.request_counts[client_ip] = [current_time]
            
        return await call_next(request)

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application startup - Initializing services")
    print(f"\n{'='*50}")
    print(f"SERVER IS NOW RUNNING ON PORT {settings.PORT}")
    print(f"{'='*50}\n")
    
    # Initialize security monitoring using async context manager
    async with async_session() as db:
        try:
            SecurityMonitor(db)
            logger.info("Security monitoring initialized")
        except Exception as e:
            logger.error(f"Error initializing security monitor: {e}")
    
    yield
    
    # Shutdown
    logger.info("Application shutdown - Terminating services")


# Initialize FastAPI app
app = FastAPI(
    title="ReFocused API",
    description="Backend API for the ReFocused productivity application",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Register exception handlers
register_exception_handlers(app)

# HTTPS will be handled by AWS infrastructure (ALB/CloudFront)

# CORS must be the FIRST middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOWED_METHODS,
    allow_headers=settings.CORS_ALLOWED_HEADERS,
)

# Add transaction middleware (must be early in the chain to have access to the DB)
app.add_middleware(TransactionMiddleware)

# Add rate limiting
if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(
        RateLimitMiddleware, 
        max_requests=settings.RATE_LIMIT_MAX_REQUESTS, 
        timeframe_seconds=settings.RATE_LIMIT_PERIOD_SECONDS
    )

# Add security middleware
app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(SQLInjectionProtectionMiddleware)
app.add_middleware(UserDataIsolationMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"] if not settings.is_production() else settings.TRUSTED_HOSTS)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Add compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API router
app.include_router(api_router, prefix="/api/v1")

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    request.state.start_time = start_time
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Google OAuth COOP middleware
@app.middleware("http")
async def google_oauth_coop_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # Set COOP headers to allow Google OAuth popups
    if "/auth/google" in str(request.url) or request.headers.get("referer", "").find("accounts.google.com") != -1:
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
    else:
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    
    return response

# Security monitoring middleware
@app.middleware("http")
async def security_monitoring(request: Request, call_next):
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
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
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

# Root endpoint
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