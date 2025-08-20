"""
Production monitoring middleware for correlation IDs, logging, and metrics.
"""

import time
import uuid
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from app.monitoring.metrics import metrics
from app.core.config import settings
from app.monitoring.logging_config import (
    log_request_start, log_request_end, log_security_event
)
from app.utils.security import get_client_ip


class ProductionMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive monitoring middleware that handles:
    - Correlation ID generation and tracking
    - Request/response logging with structured data
    - Metrics collection for monitoring and alerting
    - Performance tracking
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.skip_paths = {
            "/health", "/health/", "/metrics", "/metrics/",
            "/docs", "/redoc", "/openapi.json"
        }
    
    async def dispatch(self, request: Request, call_next):
        # Skip monitoring for health checks and internal endpoints
        if request.url.path in self.skip_paths or request.method == "OPTIONS":
            return await call_next(request)
        
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        
        # Add correlation ID to request state and structured logging context
        request.state.correlation_id = correlation_id
        # Capture app observability headers from client
        app_env_header = request.headers.get("x-app-env") or settings.APP_ENV
        client_version_header = request.headers.get("x-client-version")
        user_timezone_header = request.headers.get("x-user-timezone")

        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            request_id=correlation_id,  # Alternative name for compatibility
            method=request.method,
            path=request.url.path,
            client_ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent", "unknown"),
            app_env=app_env_header,
            client_version=client_version_header,
            user_timezone=user_timezone_header
        )
        
        # Get user ID if available from previous middleware
        user_id = getattr(request.state, 'user_id', None)
        if user_id:
            structlog.contextvars.bind_contextvars(user_id=user_id)
        
        # Start timing
        start_time = time.time()
        request.state.start_time = start_time
        
        # Log request start
        log_request_start(
            method=request.method,
            path=request.url.path,
            user_id=user_id
        )
        
        # Get request size
        request_size = int(request.headers.get("content-length", 0))
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            duration_ms = duration * 1000
            
            # Get response size
            response_size = 0
            if hasattr(response, 'headers') and 'content-length' in response.headers:
                response_size = int(response.headers['content-length'])
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = correlation_id  # Alternative name
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            
            # Record metrics
            self._record_request_metrics(
                request, response, duration, request_size, response_size
            )
            
            # Log request completion
            log_request_end(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=user_id
            )
            
            # Log slow requests
            if duration > 5.0:  # Requests taking more than 5 seconds
                logger = structlog.get_logger("performance")
                logger.warning(
                    "Slow request detected",
                    duration_seconds=duration,
                    threshold_seconds=5.0
                )
            
            return response
            
        except Exception as e:
            # Calculate duration for failed requests
            duration = time.time() - start_time
            duration_ms = duration * 1000
            
            # Log error
            logger = structlog.get_logger("api.error")
            logger.error(
                "Request failed",
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=duration_ms
            )
            
            # Record error metrics
            metrics.record_error(
                error_type=type(e).__name__,
                endpoint=self._normalize_endpoint(request.url.path)
            )
            
            # Re-raise the exception
            raise e
        
        finally:
            # Clear structured logging context
            structlog.contextvars.clear_contextvars()
    
    def _record_request_metrics(self, request: Request, response: Response, duration: float, request_size: int, response_size: int):
        """Record comprehensive request metrics."""
        endpoint = self._normalize_endpoint(request.url.path)
        
        metrics.record_http_request(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
            duration=duration,
            request_size=request_size,
            response_size=response_size
        )
        
        # Record additional metrics based on endpoint
        if request.url.path.startswith("/api/v1/auth/"):
            self._record_auth_metrics(request, response)
        elif response.status_code >= 400:
            self._record_error_metrics(request, response)
    
    def _record_auth_metrics(self, request: Request, response: Response):
        """Record authentication-specific metrics."""
        method = "unknown"
        result = "error"
        
        if "login" in request.url.path or "token" in request.url.path:
            method = "login"
        elif "register" in request.url.path:
            method = "register"
        elif "refresh" in request.url.path:
            method = "refresh"
        elif "logout" in request.url.path:
            method = "logout"
        
        if response.status_code == 200 or response.status_code == 201:
            result = "success"
        elif response.status_code == 401:
            result = "failure"
        
        metrics.record_auth_attempt(method, result)
        
        # Log suspicious auth activity
        if result == "failure":
            log_security_event(
                event_type="auth_failure",
                ip_address=get_client_ip(request),
                details={"endpoint": request.url.path, "method": method}
            )
    
    def _record_error_metrics(self, request: Request, response: Response):
        """Record error-specific metrics."""
        endpoint = self._normalize_endpoint(request.url.path)
        
        if response.status_code >= 500:
            error_type = "server_error"
        elif response.status_code >= 400:
            error_type = "client_error"
        else:
            error_type = "unknown"
        
        metrics.record_error(error_type, endpoint)
        
        # Log security events for specific error patterns
        if response.status_code == 403:
            log_security_event(
                event_type="access_denied",
                ip_address=get_client_ip(request),
                details={"endpoint": request.url.path}
            )
    
    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics (remove IDs, etc.)."""
        # Replace numeric IDs with placeholders to reduce cardinality
        import re
        
        # Replace UUIDs
        path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{uuid}', path)
        
        # Replace numeric IDs
        path = re.sub(r'/\d+(?=/|$)', '/{id}', path)
        
        # Limit path length to prevent memory issues
        if len(path) > 100:
            path = path[:97] + "..."
        
        return path


class HealthCheckMiddleware(BaseHTTPMiddleware):
    """Middleware for health check endpoints."""
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await self._health_check()
        elif request.url.path == "/health/ready":
            return await self._readiness_check()
        elif request.url.path == "/health/live":
            return await self._liveness_check()
        
        return await call_next(request)
    
    async def _health_check(self) -> Response:
        """Basic health check."""
        from fastapi.responses import JSONResponse
        
        try:
            # Check database connectivity
            from app.db.database import async_session
            async with async_session() as db:
                await db.execute("SELECT 1")
            
            # Set health status
            metrics.set_health_status(True)
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "timestamp": time.time(),
                    "version": "1.0.0"
                }
            )
        except Exception as e:
            metrics.set_health_status(False)
            
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": time.time()
                }
            )
    
    async def _readiness_check(self) -> Response:
        """Readiness probe for Kubernetes."""
        from fastapi.responses import JSONResponse
        
        # Check if app is ready to serve traffic
        # This could include checking external dependencies
        return JSONResponse(
            status_code=200,
            content={"status": "ready"}
        )
    
    async def _liveness_check(self) -> Response:
        """Liveness probe for Kubernetes."""
        from fastapi.responses import JSONResponse
        
        # Simple liveness check
        return JSONResponse(
            status_code=200,
            content={"status": "alive"}
        ) 