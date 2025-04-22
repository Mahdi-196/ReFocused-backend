from fastapi import FastAPI, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from strawberry.fastapi import GraphQLRouter
import time
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from sqlalchemy.orm import Session
import logging

from app.core.config import settings
from app.api.v1.api import api_router
from app.graphql import schema, get_context
from app.core.security_config import security_config
from app.core.security_middleware import (
    SecurityMiddleware,
    RequestValidationMiddleware,
    SQLInjectionProtectionMiddleware
)
from app.core.security_monitor import SecurityMonitor
from app.db.database import get_db
from app.core.auth import get_current_user

# Basic logging setup
logging.basicConfig(
    level=security_config.SECURITY_LOG_LEVEL,
    format=security_config.SECURITY_LOG_FORMAT,
    filename=security_config.SECURITY_LOG_PATH
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
        if settings.is_development() and not settings.SECURITY.RATE_LIMIT_ENABLED:
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

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Set security headers
        if settings.SECURITY.SECURITY_HSTS_ENABLED and settings.is_production():
            # TODO: Maybe adjust HSTS max age based on testing
            max_age = settings.SECURITY.SECURITY_HSTS_MAX_AGE
            include_subdomains = settings.SECURITY.SECURITY_HSTS_INCLUDE_SUBDOMAINS
            preload = settings.SECURITY.SECURITY_HSTS_PRELOAD
            
            hsts_value = f"max-age={max_age}"
            if include_subdomains:
                hsts_value += "; includeSubDomains"
            if preload:
                hsts_value += "; preload"
                
            response.headers["Strict-Transport-Security"] = hsts_value
        
        # Basic security headers
        if settings.SECURITY.SECURITY_FRAME_DENY:
            response.headers["X-Frame-Options"] = "DENY"
            
        if settings.SECURITY.SECURITY_XSS_PROTECTION:
            response.headers["X-XSS-Protection"] = "1; mode=block"
            
        if settings.SECURITY.SECURITY_CONTENT_TYPE_NOSNIFF:
            response.headers["X-Content-Type-Options"] = "nosniff"
            
        # TODO: Fine-tune CSP based on actual needs
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; style-src 'self';"
        
        # TODO: Maybe adjust referrer policy based on analytics needs
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # TODO: Review permissions policy based on feature requirements
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        
        return response

# HTTPS redirect middleware
class ConditionalHTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only enforce HTTPS in production
        # TODO: Add test to verify redirect works
        if settings.is_production() and request.url.scheme == "http":
            https_url = str(request.url).replace("http://", "https://", 1)
            return Response(
                status_code=301,  # Permanent redirect
                headers={"location": https_url},
                content="Redirecting to HTTPS"
            )
        return await call_next(request)

# Initialize FastAPI app
app = FastAPI(
    title=security_config.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs" if not security_config.is_production() else None,
    redoc_url="/redoc" if not security_config.is_production() else None
)

# Force HTTPS in production
if settings.is_production() and settings.SSL_ENABLED:
    app.add_middleware(HTTPSRedirectMiddleware)
else:
    app.add_middleware(ConditionalHTTPSRedirectMiddleware)

# Set up CORS middleware with more secure configuration
origins = security_config.CORS_ALLOW_ORIGINS

if settings.is_development():
    origins.append("http://localhost:3000")  # Allow localhost in development

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=security_config.CORS_ALLOW_CREDENTIALS,
    allow_methods=security_config.CORS_ALLOW_METHODS,
    allow_headers=security_config.CORS_ALLOW_HEADERS,
    max_age=security_config.CORS_MAX_AGE
)

# Add security middleware
app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(SQLInjectionProtectionMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"] if not security_config.is_production() else [security_config.BACKEND_URL])
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Add rate limiting in production
if settings.SECURITY.RATE_LIMIT_ENABLED and not settings.is_development():
    app.add_middleware(
        RateLimitMiddleware, 
        max_requests=settings.SECURITY.RATE_LIMIT_MAX_REQUESTS, 
        timeframe_seconds=settings.SECURITY.RATE_LIMIT_PERIOD_SECONDS
    )

# Add compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Add GraphQL endpoint
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphiql=settings.is_development()  # Enable GraphiQL only in development
)
app.include_router(graphql_app, prefix="/graphql")

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
    db = next(get_db())
    security_monitor = SecurityMonitor(db)
    
    try:
        # Get current user if authenticated
        user = None
        try:
            user = await get_current_user(request=request, db=db)
        except:
            pass
        
        # Monitor request
        security_monitor.monitor_request(request, user.id if user else None)
        
        # Process request
        response = await call_next(request)
        
        return response
        
    except Exception as e:
        logger.error(f"Security monitoring error: {str(e)}")
        return await call_next(request)
    
    finally:
        db.close()

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

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
    logger.error(f"Global exception: {str(exc)}")
    return {"detail": "An internal server error occurred"}

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup - Security features initialized")
    
    # Initialize security monitoring
    db = next(get_db())
    try:
        security_monitor = SecurityMonitor(db)
        logger.info("Security monitoring initialized")
    finally:
        db.close()

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown - Security features terminated")

@app.get("/")
async def root():
    return {"message": "Welcome to ReFocused API"} 