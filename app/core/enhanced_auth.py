from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from fastapi import HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.db.models import User, TokenBlacklist
from app.utils.security import generate_secure_random_string

logger = logging.getLogger("enhanced_auth")

class EnhancedAuthService:
    """Professional-grade authentication service with cookies and sessions."""
    
    def __init__(self):
        self.security = HTTPBearer(auto_error=False)
    
    def create_session_tokens(self, user: User, remember_me: bool = False) -> Dict[str, Union[str, int]]:
        """Create access and refresh tokens with appropriate expiration."""
        
        # Access token - always short-lived for security
        access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "sub": user.email,  # Use email as subject (JWT standard)
                "user_id": user.id,  # Include user_id for efficient lookups
                "session_id": generate_secure_random_string(32),
                "remember_me": remember_me
            },
            expires_delta=access_expires
        )
        
        # Refresh token - longer lived, extended if remember_me
        refresh_days = settings.SESSION_REMEMBER_ME_DAYS if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
        refresh_token = create_refresh_token(
            data={
                "sub": user.email,  # Use email as subject (JWT standard)
                "user_id": user.id,  # Include user_id for efficient lookups
                "remember_me": remember_me
            },
            expires_days=refresh_days
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "refresh_expires_in": refresh_days * 24 * 60 * 60,
            "remember_me": remember_me
        }
    
    def set_auth_cookies(self, response: Response, tokens: Dict[str, Any]) -> None:
        """Set secure HTTP-only authentication cookies."""
        
        # Calculate cookie max age based on remember_me setting
        max_age = settings.COOKIE_MAX_AGE if tokens.get("remember_me") else settings.SESSION_EXPIRE_MINUTES * 60
        
        # Set access token cookie
        response.set_cookie(
            key="access_token",
            value=tokens["access_token"],
            max_age=max_age,
            httponly=settings.COOKIE_HTTPONLY,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            domain=settings.COOKIE_DOMAIN,
            path=settings.COOKIE_PATH
        )
        
        # Set refresh token cookie (longer expiration)
        response.set_cookie(
            key="refresh_token", 
            value=tokens["refresh_token"],
            max_age=tokens["refresh_expires_in"],
            httponly=True,  # Always HTTP-only for refresh tokens
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            domain=settings.COOKIE_DOMAIN,
            path=settings.COOKIE_PATH
        )
        
        # Set session info cookie (not HTTP-only for frontend access)
        response.set_cookie(
            key="auth_session",
            value="true",
            max_age=max_age,
            httponly=False,  # Frontend needs to read this
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            domain=settings.COOKIE_DOMAIN,
            path=settings.COOKIE_PATH
        )
    
    def clear_auth_cookies(self, response: Response) -> None:
        """Clear all authentication cookies."""
        cookie_names = ["access_token", "refresh_token", "auth_session"]
        
        for cookie_name in cookie_names:
            response.delete_cookie(
                key=cookie_name,
                domain=settings.COOKIE_DOMAIN,
                path=settings.COOKIE_PATH,
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAMESITE
            )
    
    def extract_token_from_request(self, request: Request) -> Optional[str]:
        """Extract token from request (cookies or Authorization header)."""
        
        # First try cookies (preferred method)
        token = request.cookies.get("access_token")
        if token:
            return token
        
        # Fallback to Authorization header for API clients
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
        
        return None
    
    def extract_refresh_token_from_request(self, request: Request) -> Optional[str]:
        """Extract refresh token from request."""
        
        # Try cookies first
        token = request.cookies.get("refresh_token")
        if token:
            return token
        
        # Fallback to custom header
        return request.headers.get("X-Refresh-Token")
    
    async def verify_and_refresh_if_needed(
        self, 
        request: Request, 
        response: Response, 
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Verify token and automatically refresh if needed."""
        
        access_token = self.extract_token_from_request(request)
        if not access_token:
            logger.debug("No access token found in request")
            return None
        
        logger.debug(f"Found token: {access_token[:50]}...")
        
        # Check for test tokens first (development/testing)
        from app.core.auth import VALID_TEST_TOKENS
        if settings.is_development() and access_token in VALID_TEST_TOKENS:
            logger.info(f"Test token detected: {access_token}")
            return {
                "user_id": 999999,
                "sub": "test@example.com",
                "type": "access",
                "test_token": True
            }
        
        try:
            # Verify access token
            payload = jwt.decode(
                access_token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            logger.debug(f"Token decoded successfully: sub={payload.get('sub')}, user_id={payload.get('user_id')}")
            
            # Check if token is blacklisted
            if await TokenBlacklist.is_blacklisted(db, access_token):
                logger.debug("Token is blacklisted")
                return None
            
            # Check if token expires soon and auto-refresh is enabled
            if settings.AUTO_REFRESH_ENABLED:
                exp_timestamp = payload.get("exp")
                if exp_timestamp:
                    # Both times must be in UTC for correct comparison
                    exp_time = datetime.utcfromtimestamp(exp_timestamp)
                    time_until_expiry = exp_time - datetime.utcnow()
                    
                    logger.debug(f"Token expires in {time_until_expiry}, threshold is {settings.AUTO_REFRESH_THRESHOLD_MINUTES} minutes")
                    
                    # If token expires within threshold, refresh automatically
                    if time_until_expiry < timedelta(minutes=settings.AUTO_REFRESH_THRESHOLD_MINUTES):
                        logger.info(f"Auto-refreshing token for user {payload.get('sub')} (expires in {time_until_expiry})")
                        return await self.refresh_token_flow(request, response, db)
            
            logger.debug("Token verification successful")
            return payload
            
        except jwt.ExpiredSignatureError:
            # Token expired, try to refresh
            logger.info("Token expired, attempting refresh")
            return await self.refresh_token_flow(request, response, db)
        except JWTError as e:
            # Invalid token
            logger.debug(f"JWT validation error: {str(e)}")
            return None
    
    async def refresh_token_flow(
        self,
        request: Request,
        response: Response,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Handle token refresh flow."""
        
        refresh_token = self.extract_refresh_token_from_request(request)
        if not refresh_token:
            return None
        
        try:
            # Verify refresh token
            payload = jwt.decode(
                refresh_token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            if payload.get("type") != "refresh":
                return None
            
            # Check if refresh token is blacklisted
            if await TokenBlacklist.is_blacklisted(db, refresh_token):
                return None
            
            # Get user - handle both user_id and email-based lookups
            user_id = payload.get("user_id")
            if user_id:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
            else:
                # Fallback to email-based lookup
                email = payload.get("sub")
                if email:
                    result = await db.execute(select(User).where(User.email == email))
                    user = result.scalar_one_or_none()
                else:
                    user = None
            
            if not user or not user.is_active:
                return None
            
            # Create new tokens
            remember_me = payload.get("remember_me", False)
            new_tokens = self.create_session_tokens(user, remember_me)
            
            # Set new cookies
            self.set_auth_cookies(response, new_tokens)
            
            # Blacklist old refresh token
            exp_time = datetime.fromtimestamp(payload["exp"])
            await TokenBlacklist.add_token(db, refresh_token, exp_time)
            
            logger.info(f"Token refreshed successfully for user {user.id}")
            
            # Return new access token payload
            new_payload = jwt.decode(
                new_tokens["access_token"],
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            return new_payload
            
        except (JWTError, ValueError):
            return None
    
    async def get_current_user_from_request(
        self,
        request: Request,
        response: Response,
        db: AsyncSession
    ) -> Optional[User]:
        """Get current user from request with automatic refresh."""
        
        logger.debug(f"Getting user from request: {request.url.path}")
        
        payload = await self.verify_and_refresh_if_needed(request, response, db)
        if not payload:
            logger.debug("No valid payload from token verification")
            return None
        
        # Handle test tokens (development only)
        if payload.get("test_token") and settings.is_development():
            logger.info("Returning test user for development token")
            from app.core.auth import create_test_user
            return create_test_user()
        
        try:
            # Try to get user_id from payload first (new format)
            user_id = payload.get("user_id")
            if user_id:
                logger.debug(f"Looking up user by ID: {user_id}")
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                
                if user and user.is_active:
                    logger.debug(f"Found active user by ID: {user.email}")
                    return user
                elif user:
                    logger.debug(f"Found inactive user by ID: {user.email}")
                else:
                    logger.debug(f"No user found with ID: {user_id}")
            
            # Fallback to email-based lookup (legacy format)
            email = payload.get("sub")
            if email:
                logger.debug(f"Looking up user by email: {email}")
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()
                
                if user and user.is_active:
                    logger.debug(f"Found active user by email: {user.email}")
                    return user
                elif user:
                    logger.debug(f"Found inactive user by email: {user.email}")
                else:
                    logger.debug(f"No user found with email: {email}")
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error getting user from token payload: {e}")
        
        logger.debug("No user found from token")
        return None

# Global service instance
enhanced_auth_service = EnhancedAuthService() 