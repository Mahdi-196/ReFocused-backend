from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import logging
from typing import Dict, List
import re
from app.core.config import settings
from app.utils.security import get_client_ip, validate_content_type
from app.db.database import async_session
from app.core.auth import get_current_user_from_token
from app.caching.redis_cache import cache

logger = logging.getLogger("security")

class UnifiedSecurityMiddleware(BaseHTTPMiddleware):
    """Unified middleware combining security, rate limiting, and validation for better performance."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.rate_limit_store: Dict[str, List[float]] = {}
        self.ip_blocklist: Dict[str, float] = {}
        self.max_request_size = 10 * 1024 * 1024  # 10MB
        
        # Pre-compile SQL injection patterns for performance
        self.sql_patterns = [
            re.compile(r"\bunion\s+select\b", re.IGNORECASE),
            re.compile(r"\bor\s+1\s*=\s*1\b", re.IGNORECASE),
            re.compile(r"\band\s+1\s*=\s*1\b", re.IGNORECASE),
            re.compile(r";.*?(drop|delete|insert|update)\s+", re.IGNORECASE),
            re.compile(r"/\*.*?\*/", re.IGNORECASE),
            re.compile(r"--.*$", re.IGNORECASE | re.MULTILINE),
        ]
        
    async def dispatch(self, request: Request, call_next):
        # Skip middleware for static/health endpoints and debug endpoints
        skip_paths = ["/health", "/docs", "/redoc", "/openapi.json"]
        debug_paths = ["/debug/", "/api/v1/time/debug/"]
        
        if (request.url.path in skip_paths or 
            request.method == "OPTIONS" or
            any(debug_path in request.url.path for debug_path in debug_paths)):
            return await call_next(request)
        
        start_time = time.time()
        request.state.start_time = start_time
        
        client_ip = get_client_ip(request)
        
        # 1. IP Blocking Check (fastest check first)
        # DISABLED - skip all IP blocking
        # if client_ip in self.ip_blocklist:
        #     if time.time() < self.ip_blocklist[client_ip]:
        #         return self._rate_limit_response()
        #     else:
        #         del self.ip_blocklist[client_ip]
        
        # 2. Global Rate Limiting (token bucket via Redis if enabled)
        if settings.RATE_LIMIT_ENABLED:
            limited, retry_after = await self._check_token_bucket(client_ip)
            if limited:
                return Response(
                    content='{"detail": "Rate limit exceeded"}',
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    media_type="application/json",
                    headers={
                        "Retry-After": str(retry_after),
                        settings.API_RATE_LIMIT_HEADER: str(settings.GLOBAL_RATE_LIMIT_CAPACITY),
                        settings.API_RATE_LIMIT_RESET: str(int(time.time() + retry_after)),
                    },
                )
        
        # 3. Request Validation
        validation_response = await self._validate_request(request, client_ip)
        if validation_response:
            return validation_response
        
        # 4. SQL Injection Check
        if self._check_sql_injection(request, client_ip):
            return Response(
                content="Malicious request detected",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # 5. Add user context if authenticated
        await self._add_user_context(request)
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        self._add_security_headers(response, client_ip)
        
        # Log if needed
        if settings.SECURITY_LOG_ENABLED:
            self._log_request(request, response, client_ip, time.time() - start_time)
        
        return response
    
    async def _check_token_bucket(self, client_ip: str) -> tuple[bool, int]:
        """Redis-backed token bucket. Returns (is_limited, retry_after_seconds)."""
        capacity = settings.GLOBAL_RATE_LIMIT_CAPACITY
        refill_rate = settings.GLOBAL_RATE_LIMIT_REFILL_RATE

        # Keys
        key_tokens = f"rl:bucket:ip:{client_ip}:tokens"
        key_ts = f"rl:bucket:ip:{client_ip}:ts"

        now = time.time()
        retry_after_seconds = 1

        if cache.enabled:
            # Load current state
            raw_tokens = await cache.get(key_tokens)
            raw_ts = await cache.get(key_ts)

            try:
                tokens = float(raw_tokens) if raw_tokens is not None else float(capacity)
            except Exception:
                tokens = float(capacity)
            try:
                last_ts = float(raw_ts) if raw_ts is not None else now
            except Exception:
                last_ts = now

            # Refill
            elapsed = max(0.0, now - last_ts)
            tokens = min(float(capacity), tokens + elapsed * float(refill_rate))

            if tokens < 1.0:
                # Compute wait time until 1 token
                need = 1.0 - tokens
                retry_after_seconds = max(1, int(need / float(refill_rate))) if refill_rate > 0 else 1
                # Persist updated timestamp so future refills work
                await cache.set(key_ts, str(now), ttl=3600, serialize_method="pickle")
                await cache.set(key_tokens, str(tokens), ttl=3600, serialize_method="pickle")
                return True, retry_after_seconds

            # Consume one token
            tokens -= 1.0
            await cache.set(key_ts, str(now), ttl=3600, serialize_method="pickle")
            await cache.set(key_tokens, str(tokens), ttl=3600, serialize_method="pickle")
            return False, 0

        # Fallback: no Redis, allow traffic (development single-process can opt to add in-memory if desired)
        return False, 0
    
    async def _validate_request(self, request: Request, client_ip: str) -> Response | None:
        """Validate request size and content type."""
        # Check request size
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
        
        return None
    
    def _check_sql_injection(self, request: Request, client_ip: str) -> bool:
        """Check for SQL injection patterns."""
        # Check URL parameters
        query_params = str(request.query_params)
        if any(pattern.search(query_params) for pattern in self.sql_patterns):
            logger.critical(f"SQL injection attempt in URL from {client_ip}: {query_params}")
            return True
        
        return False
    
    async def _add_user_context(self, request: Request):
        """Add user context to request state if authenticated."""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                async with async_session() as db:
                    user = await get_current_user_from_token(token, db)
                    request.state.current_user = user
                    request.state.user_id = user.id
            except Exception:
                pass  # Let endpoints handle authentication
    
    def _add_security_headers(self, response: Response, client_ip: str):
        """Add security headers to response."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers[settings.API_VERSION_HEADER] = "1.0"
        
        if settings.is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Rate limit headers
        if settings.RATE_LIMIT_ENABLED and client_ip in self.rate_limit_store:
            remaining = settings.RATE_LIMIT_MAX_REQUESTS - len(self.rate_limit_store[client_ip])
            reset_time = self.rate_limit_store[client_ip][0] + settings.RATE_LIMIT_PERIOD_SECONDS
            response.headers[settings.API_RATE_LIMIT_REMAINING] = str(remaining)
            response.headers[settings.API_RATE_LIMIT_RESET] = str(int(reset_time))
            response.headers[settings.API_RATE_LIMIT_HEADER] = str(settings.RATE_LIMIT_MAX_REQUESTS)
    
    def _rate_limit_response(self) -> Response:
        """Return rate limit exceeded response."""
        return Response(
            content="Too many requests. Please try again later.",
            status_code=429
        )
    
    def _log_request(self, request: Request, response: Response, client_ip: str, response_time: float):
        """Log security event."""
        log_data = {
            "client_ip": client_ip,
            "method": request.method,
            "path": str(request.url),
            "status_code": response.status_code,
            "response_time": response_time
        }
        
        if response.status_code >= 500:
            logger.error(f"Security event: {log_data}")
        elif response.status_code >= 400:
            logger.warning(f"Security event: {log_data}")
        else:
            logger.info(f"Security event: {log_data}") 