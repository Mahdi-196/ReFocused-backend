from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import logging
from typing import Dict, List, Any, Optional
import re
from app.core.config import settings
from app.utils.security import get_client_ip, validate_content_type
from app.db.database import async_session
from app.core.auth import get_current_user_from_token

logger = logging.getLogger("security")

class SecurityMiddleware(BaseHTTPMiddleware):
    """Enhanced security middleware with user context."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.rate_limit_store: Dict[str, List[float]] = {}
        self.ip_blocklist: Dict[str, float] = {}
        
    async def dispatch(self, request: Request, call_next):
        # Skip security checks for health endpoints
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        client_ip = get_client_ip(request)
        
        # Check if IP is blocked
        if client_ip in self.ip_blocklist:
            if time.time() < self.ip_blocklist[client_ip]:
                return Response(
                    content="Too many requests. Please try again later.",
                    status_code=429
                )
            else:
                del self.ip_blocklist[client_ip]
        
        # Rate limiting
        if settings.RATE_LIMIT_ENABLED:
            current_time = time.time()
            if client_ip not in self.rate_limit_store:
                self.rate_limit_store[client_ip] = []
            
            # Clean old requests
            self.rate_limit_store[client_ip] = [
                t for t in self.rate_limit_store[client_ip]
                if current_time - t < settings.RATE_LIMIT_PERIOD_SECONDS
            ]
            
            # Check rate limit
            if len(self.rate_limit_store[client_ip]) >= settings.RATE_LIMIT_MAX_REQUESTS:
                self.ip_blocklist[client_ip] = current_time + settings.RATE_LIMIT_BLOCK_DURATION
                return Response(
                    content="Too many requests. Please try again later.",
                    status_code=429
                )
            
            self.rate_limit_store[client_ip].append(current_time)
        
        # Add security headers
        response = await call_next(request)
        
        # Standard security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # HSTS header for HTTPS
        if settings.is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # API Version
        response.headers[settings.API_VERSION_HEADER] = "1.0"
        
        # Rate Limit Headers
        if settings.RATE_LIMIT_ENABLED and client_ip in self.rate_limit_store:
            remaining = settings.RATE_LIMIT_MAX_REQUESTS - len(self.rate_limit_store[client_ip])
            reset_time = self.rate_limit_store[client_ip][0] + settings.RATE_LIMIT_PERIOD_SECONDS
            response.headers[settings.API_RATE_LIMIT_REMAINING] = str(remaining)
            response.headers[settings.API_RATE_LIMIT_RESET] = str(int(reset_time))
            response.headers[settings.API_RATE_LIMIT_HEADER] = str(settings.RATE_LIMIT_MAX_REQUESTS)
        
        # Security logging
        if settings.SECURITY_LOG_ENABLED:
            self.log_security_event(request, response, client_ip)
        
        return response
    
    def log_security_event(self, request: Request, response: Response, client_ip: str):
        log_data = {
            "timestamp": time.time(),
            "client_ip": client_ip,
            "method": request.method,
            "path": str(request.url),
            "status_code": response.status_code,
            "user_agent": request.headers.get("user-agent", ""),
            "referer": request.headers.get("referer", ""),
            "content_length": response.headers.get("content-length", "0"),
            "response_time": time.time() - request.state.start_time
        }
        
        # Log with appropriate level based on status code
        if response.status_code >= 500:
            logger.error(f"Security event: {log_data}")
        elif response.status_code >= 400:
            logger.warning(f"Security event: {log_data}")
        else:
            logger.info(f"Security event: {log_data}")

class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate incoming requests with user context awareness."""
    
    def __init__(self, app):
        super().__init__(app)
        self.max_request_size = 10 * 1024 * 1024  # 10MB limit
        
    async def dispatch(self, request: Request, call_next):
        # Skip validation for auth endpoints and health checks
        if any(path in request.url.path for path in ["/auth/", "/health", "/docs", "/redoc"]):
            return await call_next(request)
        
        client_ip = get_client_ip(request)
        
        # Validate request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_request_size:
            logger.warning(f"Request too large from {client_ip}: {content_length} bytes")
            return Response(
                content="Request too large",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )
        
        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            if not validate_content_type(content_type):
                logger.warning(f"Invalid content type from {client_ip}: {content_type}")
                return Response(
                    content="Invalid content type",
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
                )
        
        # Add user context to request state if authenticated
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                async with async_session() as db:
                    user = await get_current_user_from_token(token, db)
                    request.state.current_user = user
                    request.state.user_id = user.id
            except Exception:
                # Don't fail here, let the endpoint handle authentication
                pass
        
        return await call_next(request)

class SQLInjectionProtectionMiddleware(BaseHTTPMiddleware):
    """Enhanced SQL injection protection with user-aware logging."""
    
    def __init__(self, app):
        super().__init__(app)
        # SQL injection patterns - more specific to avoid false positives
        self.sql_patterns = [
            r"(\bunion\s+select\b)",  # Union-based injection
            r"(\bor\s+1\s*=\s*1\b)",  # Classic OR 1=1
            r"(\band\s+1\s*=\s*1\b)",  # Classic AND 1=1
            r"(;.*?(drop|delete|insert|update)\s+)",  # Command injection
            r"(/\*.*?\*/)",  # SQL comments
            r"(--.*$)",  # SQL line comments
            r"(\bexec\s*\()",  # Code execution
        ]
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.sql_patterns]
    
    async def dispatch(self, request: Request, call_next):
        client_ip = get_client_ip(request)
        user_id = getattr(request.state, 'user_id', None)
        
        # Check URL parameters
        query_params = str(request.query_params)
        if self._contains_sql_injection(query_params):
            logger.critical(f"SQL injection attempt in URL from {client_ip} (user: {user_id}): {query_params}")
            return Response(
                content="Malicious request detected",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Check request body for POST/PUT requests (skip for auth endpoints)
        if request.method in ["POST", "PUT", "PATCH"] and "/auth/" not in request.url.path:
            try:
                body = await request.body()
                if body:
                    body_str = body.decode('utf-8', errors='ignore')
                    
                    # Skip JSON content type as it's structured data
                    content_type = request.headers.get("content-type", "")
                    if "application/json" not in content_type and self._contains_sql_injection(body_str):
                        logger.critical(f"SQL injection attempt in body from {client_ip} (user: {user_id})")
                        return Response(
                            content="Malicious request detected",
                            status_code=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # Recreate request with body for downstream handlers
                    async def receive():
                        return {"type": "http.request", "body": body}
                    request._receive = receive
            except Exception as e:
                logger.error(f"Error checking request body: {str(e)}")
        
        return await call_next(request)
    
    def _contains_sql_injection(self, text: str) -> bool:
        """Check if text contains SQL injection patterns."""
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False

class UserDataIsolationMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure proper user data isolation."""
    
    async def dispatch(self, request: Request, call_next):
        # Only apply to API endpoints that modify data
        if not request.url.path.startswith("/api/v1/") or request.method in ["GET", "OPTIONS"]:
            return await call_next(request)
        
        # Skip auth endpoints
        if "/auth/" in request.url.path:
            return await call_next(request)
        
        # Ensure user is authenticated for data modification
        if not hasattr(request.state, 'user_id'):
            return Response(
                content="Authentication required",
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        response = await call_next(request)
        
        # Add user context to response headers for debugging (in dev mode only)
        if settings.is_development():
            response.headers["X-User-Context"] = str(request.state.user_id)
        
        return response 