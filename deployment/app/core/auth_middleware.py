from fastapi import Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from typing import Optional, List
import re

from app.core.enhanced_auth import enhanced_auth_service
from app.db.database import async_session
from app.core.config import settings
from app.utils.security import get_client_ip

logger = logging.getLogger("auth_middleware")

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Professional authentication middleware with automatic redirects and session management."""
    
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        
        # Paths that don't require authentication
        self.public_paths = [
            "/",
            "/health",
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/google",
            "/api/v1/auth/refresh",
            "/debug",
            "/security"
        ]
        
        # Paths that require authentication but should return JSON errors (API endpoints)
        self.api_path_pattern = re.compile(r"^/api/v1/(?!auth)")
        
        # Frontend paths that should redirect to login when not authenticated
        self.frontend_paths = [
            "/dashboard",
            "/goals",
            "/habits", 
            "/journal",
            "/profile",
            "/settings"
        ]
    
    def is_public_path(self, path: str) -> bool:
        """Check if path is publicly accessible."""
        result = any(path.startswith(public_path) for public_path in self.public_paths)
        logger.info(f"🔍 AUTH_MIDDLEWARE: is_public_path({path}) = {result}")
        if not result:
            logger.info(f"🔍 AUTH_MIDDLEWARE: Public paths: {self.public_paths}")
        return result
    
    def is_api_path(self, path: str) -> bool:
        """Check if path is an API endpoint."""
        return bool(self.api_path_pattern.match(path))
    
    def is_frontend_path(self, path: str) -> bool:
        """Check if path is a frontend route."""
        return any(path.startswith(frontend_path) for frontend_path in self.frontend_paths)
    
    async def dispatch(self, request: Request, call_next):
        """Process authentication for each request."""

        import time
        logger.info(f"🔍 AUTH_MIDDLEWARE: Starting auth check for {request.method} {request.url.path}")
        auth_start = time.time()

        path = request.url.path
        method = request.method

        # Skip OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            logger.info(f"🔍 AUTH_MIDDLEWARE: Skipping OPTIONS request")
            return await call_next(request)

        # Skip public paths
        if self.is_public_path(path):
            logger.info(f"🔍 AUTH_MIDDLEWARE: Skipping public path: {path}")
            return await call_next(request)
        
        # Create response object to potentially set cookies
        response = None
        user = None
        
        # Check authentication
        logger.info(f"🔍 AUTH_MIDDLEWARE: Creating database session...")
        db_start = time.time()

        async with async_session() as db:
            db_time = time.time() - db_start
            logger.info(f"🔍 AUTH_MIDDLEWARE: DB session created in {db_time:.3f}s")

            try:
                logger.info(f"🔍 AUTH_MIDDLEWARE: Calling enhanced_auth_service...")
                auth_service_start = time.time()

                # Create a temporary response to collect cookies
                temp_response = Response()
                user = await enhanced_auth_service.get_current_user_from_request(
                    request, temp_response, db
                )

                auth_service_time = time.time() - auth_service_start
                logger.info(f"🔍 AUTH_MIDDLEWARE: Enhanced auth service took {auth_service_time:.3f}s")
                
                # Debug logging for API paths
                if self.is_api_path(path):
                    logger.info(f"API path {path}: user={'found' if user else 'not found'}")
                
                # If we got a user and cookies were set (token refresh), we need to forward them
                if temp_response.headers.get("set-cookie"):
                    # Process the request first
                    response = await call_next(request)
                    # Add any auth cookies from temp_response
                    for cookie_header in temp_response.headers.getlist("set-cookie"):
                        response.headers.append("set-cookie", cookie_header)
                    return response
                
            except Exception as e:
                logger.error(f"Auth middleware error: {str(e)}")
                user = None
        
        # Handle unauthenticated requests
        if not user:
            if self.is_api_path(path):
                # API endpoints get JSON error response
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "detail": "Authentication required",
                        "error": "unauthorized",
                        "login_url": "/api/v1/auth/login"
                    },
                    headers={"WWW-Authenticate": "Bearer"}
                )
            elif self.is_frontend_path(path):
                # Frontend paths redirect to login with return URL
                login_url = f"/?redirect={path}"
                return RedirectResponse(url=login_url, status_code=302)
        
        # User is authenticated, proceed with request
        # Store user in request state for easy access in endpoints
        request.state.user = user
        
        # Process the request
        if response is None:
            logger.info(f"🔍 AUTH_MIDDLEWARE: Calling call_next for authenticated user...")
            call_start = time.time()
            response = await call_next(request)
            call_time = time.time() - call_start
            logger.info(f"🔍 AUTH_MIDDLEWARE: call_next took {call_time:.3f}s")

        total_time = time.time() - auth_start
        logger.info(f"🔍 AUTH_MIDDLEWARE: Total auth middleware time: {total_time:.3f}s")
        return response

class SessionAuthenticationMiddleware(BaseHTTPMiddleware):
    """Simplified session-based auth middleware for cookie management."""
    
    async def dispatch(self, request: Request, call_next):
        """Handle session authentication and automatic refresh."""

        import time
        logger.info(f"🔍 SESSION_AUTH: Starting session auth for {request.method} {request.url.path}")
        session_start = time.time()

        # Skip for certain paths
        path = request.url.path
        if (request.method == "OPTIONS" or
            path.startswith("/health") or
            path.startswith("/docs") or
            path.startswith("/redoc") or
            path.startswith("/openapi.json") or
            path.startswith("/api/v1/auth/")):  # Skip ALL auth endpoints
            logger.info(f"🔍 SESSION_AUTH: Skipping auth path: {path}")
            return await call_next(request)
        
        # CSRF protection for cookie-only flows on state-changing requests
        if settings.CSRF_ENABLED and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            auth_header = request.headers.get("Authorization", "")
            # Skip CSRF for API clients using Bearer auth
            if not auth_header.startswith("Bearer "):
                # Skip CSRF on unauthenticated requests (no session cookies yet), e.g., login/register
                has_session_cookies = bool(
                    request.cookies.get("auth_session") or
                    request.cookies.get("access_token") or
                    request.cookies.get("refresh_token")
                )
                is_auth_path = path.startswith("/api/v1/auth/") or path == "/auth/refresh"
                if has_session_cookies and not is_auth_path:
                    csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)
                    csrf_cookie = request.cookies.get("csrf_token")
                    if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
                        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")

        # Create response and check/refresh auth
        response = await call_next(request)
        
        # For authenticated endpoints, try to refresh tokens if needed
        if hasattr(request.state, "user") and request.state.user:
            async with async_session() as db:
                try:
                    # This will automatically refresh tokens if needed
                    await enhanced_auth_service.verify_and_refresh_if_needed(
                        request, response, db
                    )
                except Exception as e:
                    logger.warning(f"Token refresh failed: {str(e)}")
        
        return response 