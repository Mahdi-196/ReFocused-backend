import time
import uuid
import re
from typing import Dict, List, Optional, Set
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from app.monitoring.metrics import metrics
from app.monitoring.logging_config import log_security_event, get_logger
from app.utils.security import get_client_ip
from app.core.config import settings


class ProductionMiddleware(BaseHTTPMiddleware):
    """
    Consolidated production middleware that efficiently handles:
    - Security validation and protection
    - Request monitoring and metrics
    - Correlation ID tracking
    - Performance monitoring
    - Rate limiting (when enabled)
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        
        # Configuration
        self.rate_limit_enabled = settings.RATE_LIMIT_ENABLED and settings.is_production()
        self.max_request_size = 10 * 1024 * 1024  # 10MB
        
        # In-memory stores (for production, use Redis)
        self.rate_limit_store: Dict[str, List[float]] = {}
        self.ip_blocklist: Set[str] = set()
        
        # Skip paths for monitoring and security
        self.skip_monitoring = {
            "/health", "/health/ready", "/health/live", 
            "/metrics", "/docs", "/redoc", "/openapi.json"
        }
        
        self.skip_security = {
            "/health", "/metrics", "/docs", "/redoc", "/openapi.json"
        }
        
        # Pre-compiled security patterns for performance
        self.sql_injection_patterns = [
            re.compile(r"\bunion\s+select\b", re.IGNORECASE),
            re.compile(r"\bor\s+1\s*=\s*1\b", re.IGNORECASE),
            re.compile(r";.*?(drop|delete|insert|update)\s+", re.IGNORECASE),
            re.compile(r"--.*$", re.IGNORECASE | re.MULTILINE),
        ]
        
        self.xss_patterns = [
            re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
            re.compile(r"javascript:", re.IGNORECASE),
            re.compile(r"on\w+\s*=", re.IGNORECASE),
        ]
        
        # Logger
        self.logger = get_logger("security.middleware")
    
    async def dispatch(self, request: Request, call_next):
        # Skip processing for certain paths
        skip_monitoring = request.url.path in self.skip_monitoring or request.method == "OPTIONS"
        skip_security = request.url.path in self.skip_security or request.method == "OPTIONS"
        
        if skip_monitoring and skip_security:
            return await call_next(request)
        
        # Start timing
        start_time = time.time()
        client_ip = get_client_ip(request)
        
        # Generate correlation ID for tracking
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Set up structured logging context
        if not skip_monitoring:
            structlog.contextvars.bind_contextvars(
                correlation_id=correlation_id,
                method=request.method,
                path=request.url.path,
                client_ip=client_ip
            )
        
        # Security validation
        if not skip_security:
            security_response = await self._validate_security(request, client_ip)
            if security_response:
                return security_response
        
        # Process request
        try:
            response = await call_next(request)
            
            # Add security and monitoring headers
            if not skip_monitoring:
                self._add_response_headers(response, correlation_id, start_time)
            
            # Record metrics and logging
            if not skip_monitoring:
                await self._record_metrics_and_logs(request, response, start_time, client_ip)
            
            return response
            
        except Exception as e:
            # Handle errors
            if not skip_monitoring:
                await self._handle_error(request, e, start_time, client_ip)
            raise
        
        finally:
            # Cleanup
            if not skip_monitoring:
                structlog.contextvars.clear_contextvars()
    
    async def _validate_security(self, request: Request, client_ip: str) -> Optional[Response]:
        """Consolidated security validation."""
        
        # 1. IP blocking check (if enabled)
        if client_ip in self.ip_blocklist:
            self._log_security_event("blocked_ip", client_ip, {"reason": "blocklist"})
            return self._security_error_response("Access denied")
        
        # 2. Rate limiting (if enabled)
        if self.rate_limit_enabled:
            if not self._check_rate_limit(client_ip):
                self._log_security_event("rate_limit_exceeded", client_ip)
                return self._rate_limit_response()
        
        # 3. Request size validation
        content_length = int(request.headers.get("content-length", 0))
        if content_length > self.max_request_size:
            self._log_security_event("oversized_request", client_ip, {"size": content_length})
            return self._security_error_response("Request too large")
        
        # 4. Content validation (for POST/PUT requests)
        if request.method in ["POST", "PUT", "PATCH"]:
            if await self._check_malicious_content(request, client_ip):
                return self._security_error_response("Malicious content detected")
        
        # 5. Header validation
        if self._check_malicious_headers(request, client_ip):
            return self._security_error_response("Malicious headers detected")
        
        return None
    
    def _check_rate_limit(self, client_ip: str) -> bool:
        """Simple per-IP sliding-window rate limiting in memory."""
        current_time = time.time()
        window_start = current_time - settings.RATE_LIMIT_WINDOW_SECONDS
        
        # Get or create request list for IP
        if client_ip not in self.rate_limit_store:
            self.rate_limit_store[client_ip] = []
        
        # Remove old requests
        self.rate_limit_store[client_ip] = [
            req_time for req_time in self.rate_limit_store[client_ip]
            if req_time > window_start
        ]
        
        # Check if limit exceeded
        if len(self.rate_limit_store[client_ip]) >= settings.RATE_LIMIT_MAX_REQUESTS:
            return False
        
        # Add current request
        self.rate_limit_store[client_ip].append(current_time)
        return True
    
    async def _check_malicious_content(self, request: Request, client_ip: str) -> bool:
        """Check request body for malicious content."""
        try:
            # Only check text content to avoid binary data issues
            content_type = request.headers.get("content-type", "")
            if not any(t in content_type for t in ["application/json", "application/x-www-form-urlencoded", "text/"]):
                return False

            # Read body safely and cache it in request.state for later reuse
            body = await request.body()
            # Cache the body so it can be read again by the endpoint
            request.state.cached_body = body

            if not body:
                return False
            
            try:
                body_str = body.decode("utf-8")
            except UnicodeDecodeError:
                # Binary data, skip check
                return False
            
            # Check for SQL injection
            for pattern in self.sql_injection_patterns:
                if pattern.search(body_str):
                    self._log_security_event("sql_injection_attempt", client_ip, {"pattern": pattern.pattern})
                    return True
            
            # Check for XSS
            for pattern in self.xss_patterns:
                if pattern.search(body_str):
                    self._log_security_event("xss_attempt", client_ip, {"pattern": pattern.pattern})
                    return True
            
            return False
            
        except Exception:
            # If we can't check the content, allow it through
            return False
    
    def _check_malicious_headers(self, request: Request, client_ip: str) -> bool:
        """Check headers for malicious content."""
        suspicious_headers = ["x-forwarded-host", "x-original-url", "x-rewrite-url"]
        
        for header, value in request.headers.items():
            # Check suspicious headers
            if header.lower() in suspicious_headers:
                self._log_security_event("suspicious_header", client_ip, {"header": header, "value": value})
                return True
            
            # Check for injection in common headers
            if header.lower() in ["user-agent", "referer", "x-forwarded-for"]:
                for pattern in self.xss_patterns:
                    if pattern.search(value):
                        self._log_security_event("header_injection", client_ip, {"header": header})
                        return True
        
        return False
    
    def _add_response_headers(self, response: Response, correlation_id: str, start_time: float):
        """Add security and monitoring headers."""
        duration_ms = (time.time() - start_time) * 1000
        
        # Monitoring headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        if settings.is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Rate limit informational headers if enabled
        if self.rate_limit_enabled and hasattr(self, 'rate_limit_store'):
            ip_entries = self.rate_limit_store.get(get_client_ip)
            # We cannot reliably compute remaining without request context here, so include static limit/window
            response.headers[settings.API_RATE_LIMIT_HEADER] = str(settings.RATE_LIMIT_MAX_REQUESTS)
            response.headers[settings.API_RATE_LIMIT_RESET] = str(int(time.time() + settings.RATE_LIMIT_WINDOW_SECONDS))
    
    async def _record_metrics_and_logs(self, request: Request, response: Response, start_time: float, client_ip: str):
        """Record metrics and logs efficiently."""
        duration = time.time() - start_time
        
        # Normalize endpoint for metrics
        endpoint = self._normalize_endpoint(request.url.path)
        
        # Record HTTP metrics
        metrics.record_http_request(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
            duration=duration
        )
        
        # Record auth metrics for auth endpoints
        if request.url.path.startswith("/api/v1/auth/"):
            self._record_auth_metrics(request, response)
        
        # Log slow requests
        if duration > 2.0:
            self.logger.warning(
                "Slow request",
                duration_seconds=duration,
                endpoint=endpoint,
                method=request.method
            )
        
        # Log errors
        if response.status_code >= 400:
            self.logger.warning(
                "HTTP error",
                status_code=response.status_code,
                endpoint=endpoint,
                method=request.method,
                client_ip=client_ip
            )
    
    async def _handle_error(self, request: Request, error: Exception, start_time: float, client_ip: str):
        """Handle request errors."""
        duration = time.time() - start_time
        endpoint = self._normalize_endpoint(request.url.path)
        
        # Log error
        self.logger.error(
            "Request failed",
            error_type=type(error).__name__,
            error_message=str(error),
            endpoint=endpoint,
            method=request.method,
            duration_seconds=duration,
            client_ip=client_ip
        )
        
        # Record error metric
        metrics.record_error(type(error).__name__, endpoint)
    
    def _record_auth_metrics(self, request: Request, response: Response):
        """Record authentication metrics."""
        method = "unknown"
        if "login" in request.url.path or "token" in request.url.path:
            method = "login"
        elif "register" in request.url.path:
            method = "register"
        elif "refresh" in request.url.path:
            method = "refresh"
        
        result = "success" if response.status_code < 300 else "failure"
        metrics.record_auth_attempt(method, result)
    
    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics."""
        # Replace IDs with placeholders to reduce cardinality
        path = re.sub(r'/\d+(?=/|$)', '/{id}', path)
        path = re.sub(r'/[0-9a-f-]{36}(?=/|$)', '/{uuid}', path)
        return path[:100]  # Limit length
    
    def _log_security_event(self, event_type: str, client_ip: str, details: Optional[Dict] = None):
        """Log security events."""
        log_security_event(
            event_type=event_type,
            ip_address=client_ip,
            details=details
        )
        metrics.record_security_event(event_type)
    
    def _security_error_response(self, message: str) -> Response:
        """Return security error response."""
        return Response(
            content=f'{{"detail": "{message}"}}',
            status_code=status.HTTP_403_FORBIDDEN,
            media_type="application/json"
        )
    
    def _rate_limit_response(self) -> Response:
        """Return rate limit error response."""
        return Response(
            content='{"detail": "Rate limit exceeded"}',
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            media_type="application/json",
            headers={
                "Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)
            }
        ) 