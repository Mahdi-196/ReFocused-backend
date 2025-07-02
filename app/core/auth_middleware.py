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
    """Simplified session-based auth middleware for cookie management."""
    
    async def dispatch(self, request: Request, call_next):
        """Handle session authentication and automatic refresh."""
        
        # Skip for certain paths
        path = request.url.path
        if (request.method == "OPTIONS" or 
            path.startswith("/health") or 
            path.startswith("/docs") or
            path.startswith("/redoc") or
            path.startswith("/openapi.json")):
            return await call_next(request)
        
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