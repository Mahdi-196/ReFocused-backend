from fastapi import FastAPI, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import time
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from sqlalchemy.orm import Session
import logging
from datetime import datetime
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1.api import api_router

from app.core.security_middleware import (
    SecurityMiddleware,
    RequestValidationMiddleware,
    SQLInjectionProtectionMiddleware,
    UserDataIsolationMiddleware
)
from app.core.security_monitor import SecurityMonitor
from app.db.database import get_db, async_session
from app.core.auth import get_current_user

# Basic logging setup
logging.basicConfig(
    level=settings.SECURITY_LOG_LEVEL,
    format=settings.SECURITY_LOG_FORMAT,
    filename=settings.SECURITY_LOG_PATH
)
logger = logging.getLogger("app")

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

# Security headers are handled by SecurityMiddleware


# Initialize FastAPI app
app = FastAPI(
    title="ReFocused API",
    description="Backend API for the ReFocused productivity application",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# HTTPS will be handled by AWS infrastructure (ALB/CloudFront)

# CORS middleware configuration for frontend-backend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React default
        "http://localhost:3001",  # Alternative React port
        "http://localhost:5173",  # Vite default
        "http://localhost:5174",  # Alternative Vite port
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        # Add your production frontend URL here when ready
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "User-Agent",
        "DNT",
        "Cache-Control",
        "X-Mx-ReqToken",
        "Keep-Alive",
        "X-Requested-With",
        "If-Modified-Since",
    ],
)

# Add security middleware
app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(SQLInjectionProtectionMiddleware)
app.add_middleware(UserDataIsolationMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"] if not settings.is_production() else settings.TRUSTED_HOSTS)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Add rate limiting in production
if settings.RATE_LIMIT_ENABLED and not settings.is_development():
    app.add_middleware(
        RateLimitMiddleware, 
        max_requests=settings.RATE_LIMIT_MAX_REQUESTS, 
        timeframe_seconds=settings.RATE_LIMIT_PERIOD_SECONDS
    )

# Add compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API router
app.include_router(api_router, prefix="/api/v1")

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

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    request.state.start_time = start_time
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Security monitoring middleware
@app.middleware("http")
async def security_monitoring(request: Request, call_next):
    # Skip security monitoring for auth endpoints and health checks to avoid conflicts
    if any(path in str(request.url.path) for path in ["/auth/", "/health", "/docs", "/redoc", "/openapi.json"]):
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

# Security metrics endpoint
@app.get("/security/metrics")
async def get_security_metrics(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user)  # Require authentication
):
    security_monitor = SecurityMonitor(db)
    return security_monitor.get_security_metrics()

# Security alerts endpoint
@app.get("/security/alerts")
async def get_security_alerts(
    resolved: bool = False,
    db: Session = Depends(get_db),
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
    
    return JSONResponse(
        status_code=500,
        content=error_response
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup - Security features initialized")
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
        # Session closes automatically when exiting 'async with'

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown - Security features terminated")

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