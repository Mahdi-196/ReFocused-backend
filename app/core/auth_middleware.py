from fastapi import Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from typing import Optional, List
import re
import time

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
        return any(path.startswith(public_path) for public_path in self.public_paths)
    
    def is_api_path(self, path: str) -> bool:
        """Check if path is an API endpoint."""
        return bool(self.api_path_pattern.match(path))
    
    def is_frontend_path(self, path: str) -> bool:
        """Check if path is a frontend route."""
        return any(path.startswith(frontend_path) for frontend_path in self.frontend_paths)
    
    async def dispatch(self, request: Request, call_next):
        """Process authentication for each request."""
        
        path = request.url.path
        method = request.method
        
        # Skip OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            return await call_next(request)
        
        # Skip public paths
        if self.is_public_path(path):
            return await call_next(request)
        
        # Create response object to potentially set cookies
        response = None
        user = None
        
        # Check authentication
        async with async_session() as db:
            try:
                # Create a temporary response to collect cookies
                temp_response = Response()
                user = await enhanced_auth_service.get_current_user_from_request(
                    request, temp_response, db
                )
                
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
            response = await call_next(request)
        
        return response

class SessionAuthenticationMiddleware(BaseHTTPMiddleware):
    """Simplified session-based auth middleware for cookie management.

    SECURITY NOTE: Uses a single database session per request to prevent connection
    pool exhaustion while maintaining proper transaction isolation.
    """

    async def dispatch(self, request: Request, call_next):
        """Handle session authentication and automatic refresh.

        Security measures:
        - CSRF protection on state-changing requests
        - Single DB session per request (prevents pool exhaustion)
        - Automatic token refresh with proper session management
        """
        start_time = time.time()
        path = request.url.path

        logger.info(f"🔵 [AUTH_MW START] {request.method} {path} - Session auth middleware entry")

        # Skip for certain paths
        if (request.method == "OPTIONS" or
            path.startswith("/health") or
            path.startswith("/docs") or
            path.startswith("/redoc") or
            path.startswith("/openapi.json")):
            logger.info(f"⚪ [AUTH_MW SKIP] {path} - Skipped (public path)")
            return await call_next(request)

        # CSRF protection for cookie-only flows on state-changing requests
        logger.info(f"🔒 [AUTH_MW CSRF CHECK] {path} - Checking CSRF (enabled={settings.CSRF_ENABLED})")
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
                logger.info(f"🔒 [CSRF] has_session_cookies={has_session_cookies}, is_auth_path={is_auth_path}")
                if has_session_cookies and not is_auth_path:
                    csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)
                    csrf_cookie = request.cookies.get("csrf_token")
                    if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
                        logger.warning(f"❌ [CSRF FAIL] CSRF validation failed for {path}")
                        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")

        # Process the request - endpoints create their own DB sessions via Depends(get_db)
        logger.info(f"➡️  [AUTH_MW CALLING] {path} - Calling next middleware/endpoint")
        call_start = time.time()

        response = await call_next(request)

        call_duration = time.time() - call_start
        logger.info(f"⬅️  [AUTH_MW RETURNED] {path} - Response received ({call_duration:.2f}s)")

        # For authenticated endpoints, try to refresh tokens if needed
        # Create a separate session only for token refresh (minimal operation)
        if hasattr(request.state, "user") and request.state.user:
            logger.info(f"🔄 [AUTH_MW REFRESH] {path} - Checking if token refresh needed")
            async with async_session() as db:
                try:
                    await enhanced_auth_service.verify_and_refresh_if_needed(
                        request, response, db
                    )
                    logger.info(f"✅ [AUTH_MW REFRESH] {path} - Token refresh check complete")
                except Exception as e:
                    logger.warning(f"❌ [AUTH_MW REFRESH FAIL] {path} - Token refresh failed: {str(e)}")

        total_duration = time.time() - start_time
        logger.info(f"🟢 [AUTH_MW COMPLETE] {path} - Session auth complete ({total_duration:.2f}s)")
        return response 