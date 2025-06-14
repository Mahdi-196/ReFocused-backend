from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.
    
    This middleware adds headers like:
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy
    - Content-Security-Policy (if enabled)
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        # Process the request
        response = await call_next(request)
        
        # Skip for CORS preflight requests
        if request.method == "OPTIONS":
            return response
        
        # Add security headers
        if settings.SECURITY_CONTENT_TYPE_NOSNIFF:
            response.headers["X-Content-Type-Options"] = "nosniff"
        
        if settings.SECURITY_FRAME_DENY:
            response.headers["X-Frame-Options"] = "DENY"
        
        if settings.SECURITY_XSS_PROTECTION:
            response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Add referrer policy
        if settings.SECURITY_REFERRER_POLICY:
            response.headers["Referrer-Policy"] = settings.SECURITY_REFERRER_POLICY
        
        # Add permissions policy
        if settings.SECURITY_PERMISSIONS_POLICY:
            response.headers["Permissions-Policy"] = settings.SECURITY_PERMISSIONS_POLICY
        
        # Add Content-Security-Policy header if enabled
        if settings.CSP_ENABLED and getattr(response, "body", None) is not None:
            csp_value = self._build_csp_header()
            if csp_value:
                response.headers["Content-Security-Policy"] = csp_value
        
        # Set secure cookie attribute in production
        if settings.is_production() and "Set-Cookie" in response.headers:
            self._update_cookies_security(response)
        
        return response
    
    def _build_csp_header(self) -> str:
        """Build Content-Security-Policy header value from settings."""
        directives = []
        
        for directive, value in settings.CSP_DIRECTIVES.items():
            if value:
                directives.append(f"{directive} {value}")
        
        return "; ".join(directives)
    
    def _update_cookies_security(self, response: Response) -> None:
        """Update Set-Cookie header to include security attributes."""
        if "Set-Cookie" in response.headers:
            cookies = response.headers.getlist("Set-Cookie")
            secure_cookies = []
            
            for cookie in cookies:
                if "SameSite=" not in cookie:
                    cookie += "; SameSite=Lax"
                if "Secure" not in cookie and settings.is_production():
                    cookie += "; Secure"
                if "HttpOnly" not in cookie:
                    cookie += "; HttpOnly"
                secure_cookies.append(cookie)
            
            response.headers.remove("Set-Cookie")
            for cookie in secure_cookies:
                response.headers.append("Set-Cookie", cookie) 