from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import logging
from typing import Dict, List
import re
from app.core.security_config import security_config

logger = logging.getLogger("security")

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.rate_limit_store: Dict[str, List[float]] = {}
        self.ip_blocklist: Dict[str, float] = {}
        
    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = request.client.host
        
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
        if security_config.RATE_LIMIT_ENABLED:
            current_time = time.time()
            if client_ip not in self.rate_limit_store:
                self.rate_limit_store[client_ip] = []
            
            # Clean old requests
            self.rate_limit_store[client_ip] = [
                t for t in self.rate_limit_store[client_ip]
                if current_time - t < security_config.RATE_LIMIT_PERIOD_SECONDS
            ]
            
            # Check rate limit
            if len(self.rate_limit_store[client_ip]) >= security_config.RATE_LIMIT_MAX_REQUESTS:
                self.ip_blocklist[client_ip] = current_time + security_config.RATE_LIMIT_BLOCK_DURATION
                return Response(
                    content="Too many requests. Please try again later.",
                    status_code=429
                )
            
            self.rate_limit_store[client_ip].append(current_time)
        
        # Security headers
        response = await call_next(request)
        
        # HSTS
        if security_config.SECURITY_HSTS_ENABLED:
            hsts_value = f"max-age={security_config.SECURITY_HSTS_MAX_AGE}"
            if security_config.SECURITY_HSTS_INCLUDE_SUBDOMAINS:
                hsts_value += "; includeSubDomains"
            if security_config.SECURITY_HSTS_PRELOAD:
                hsts_value += "; preload"
            response.headers["Strict-Transport-Security"] = hsts_value
        
        # X-Frame-Options
        if security_config.SECURITY_FRAME_DENY:
            response.headers["X-Frame-Options"] = "DENY"
        
        # X-XSS-Protection
        if security_config.SECURITY_XSS_PROTECTION:
            response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # X-Content-Type-Options
        if security_config.SECURITY_CONTENT_TYPE_NOSNIFF:
            response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = security_config.SECURITY_REFERRER_POLICY
        
        # Permissions Policy
        response.headers["Permissions-Policy"] = security_config.SECURITY_PERMISSIONS_POLICY
        
        # Content Security Policy
        if security_config.CSP_ENABLED:
            csp_directives = []
            for directive, sources in security_config.CSP_DIRECTIVES.items():
                csp_directives.append(f"{directive} {' '.join(sources)}")
            response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # API Version
        response.headers[security_config.API_VERSION_HEADER] = "1.0"
        
        # Rate Limit Headers
        if security_config.RATE_LIMIT_ENABLED and client_ip in self.rate_limit_store:
            remaining = security_config.RATE_LIMIT_MAX_REQUESTS - len(self.rate_limit_store[client_ip])
            reset_time = self.rate_limit_store[client_ip][0] + security_config.RATE_LIMIT_PERIOD_SECONDS
            response.headers[security_config.API_RATE_LIMIT_REMAINING] = str(remaining)
            response.headers[security_config.API_RATE_LIMIT_RESET] = str(int(reset_time))
            response.headers[security_config.API_RATE_LIMIT_HEADER] = str(security_config.RATE_LIMIT_MAX_REQUESTS)
        
        # Security logging
        if security_config.SECURITY_LOG_ENABLED:
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
    async def dispatch(self, request: Request, call_next):
        # Validate request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > security_config.MAX_UPLOAD_SIZE:
            return Response(
                content="Request entity too large",
                status_code=413
            )
        
        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT"]:
            content_type = request.headers.get("content-type", "")
            if not content_type or not any(
                ct in content_type for ct in ["application/json", "multipart/form-data"]
            ):
                return Response(
                    content="Unsupported media type",
                    status_code=415
                )
        
        # Validate API version header
        api_version = request.headers.get(security_config.API_VERSION_HEADER)
        if api_version and api_version != "1.0":
            return Response(
                content="Unsupported API version",
                status_code=400
            )
        
        return await call_next(request)

class SQLInjectionProtectionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.sql_patterns = [
            r"(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|WHERE|FROM|JOIN)",
            r"(?i)(--|#|/\*|\*/)",
            r"(?i)(OR\s+1=1|AND\s+1=1)",
            r"(?i)(EXEC|EXECUTE|EXECUTE\s+SP|EXECUTE\s+SQL)",
            r"(?i)(WAITFOR|DELAY|SLEEP)"
        ]
    
    async def dispatch(self, request: Request, call_next):
        # Check query parameters
        for param in request.query_params.values():
            if self._contains_sql_injection(param):
                return Response(
                    content="Invalid request",
                    status_code=400
                )
        
        # Check form data
        if request.method in ["POST", "PUT"]:
            form_data = await request.form()
            for value in form_data.values():
                if self._contains_sql_injection(value):
                    return Response(
                        content="Invalid request",
                        status_code=400
                    )
        
        return await call_next(request)
    
    def _contains_sql_injection(self, value: str) -> bool:
        if not isinstance(value, str):
            return False
        return any(re.search(pattern, value) for pattern in self.sql_patterns) 