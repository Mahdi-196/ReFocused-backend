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
    
    def create_session_tokens(self, user: User, remember_me: bool = False, session_started_at: Optional[datetime] = None) -> Dict[str, Union[str, int]]:
        """Create access and refresh tokens with appropriate expiration.

        Args:
            user: The user to create tokens for
            remember_me: Whether to extend session duration
            session_started_at: When the session was originally created (for absolute max timeout)
        """

        # For sliding sessions, track when the session originally started
        if session_started_at is None:
            session_started_at = datetime.utcnow()

        # Access token - always short-lived for security
        access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "sub": user.email,  # Use email as subject (JWT standard)
                "user_id": user.id,  # Include user_id for efficient lookups
                "session_id": generate_secure_random_string(32),
                "remember_me": remember_me,
                "session_started_at": session_started_at.timestamp(),  # Track original session start
                "cookie_issued_at": datetime.utcnow().timestamp()  # Track when cookies were issued
            },
            expires_delta=access_expires
        )

        # Refresh token - longer lived, extended if remember_me
        refresh_days = settings.SESSION_REMEMBER_ME_DAYS if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
        refresh_token = create_refresh_token(
            data={
                "sub": user.email,  # Use email as subject (JWT standard)
                "user_id": user.id,  # Include user_id for efficient lookups
                "remember_me": remember_me,
                "session_started_at": session_started_at.timestamp(),  # Track original session start
                "cookie_issued_at": datetime.utcnow().timestamp()  # Track when cookies were issued
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
        """Set secure HTTP-only authentication cookies with sliding session support."""

        # For sliding sessions, use a consistent 7-day expiry
        # This will be refreshed on activity, with a 60-day absolute maximum
        if settings.SLIDING_SESSION_ENABLED:
            max_age = 7 * 24 * 60 * 60  # 7 days in seconds
        else:
            # Legacy behavior based on remember_me
            max_age = settings.COOKIE_MAX_AGE if tokens.get("remember_me") else settings.SESSION_EXPIRE_MINUTES * 60

        # Use configured SameSite value directly
        # For cross-origin cookies, MUST use SameSite=None with Secure=True
        samesite_value = settings.COOKIE_SAMESITE

        # Set access token cookie
        response.set_cookie(
            key="access_token",
            value=tokens["access_token"],
            max_age=max_age,
            httponly=settings.COOKIE_HTTPONLY,
            secure=settings.COOKIE_SECURE,
            samesite=samesite_value,
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
            samesite=samesite_value,
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
            samesite=samesite_value,
            domain=settings.COOKIE_DOMAIN,
            path=settings.COOKIE_PATH
        )
        # CSRF double-submit cookie for cookie-auth flows
        if settings.CSRF_ENABLED:
            from app.utils.security import generate_secure_random_string
            csrf_token = generate_secure_random_string(32)
            response.set_cookie(
                key="csrf_token",
                value=csrf_token,
                max_age=max_age,
                httponly=False,  # Must be readable by JS to set header
                secure=settings.COOKIE_SECURE,
                samesite=samesite_value,
                domain=settings.COOKIE_DOMAIN,
                path=settings.COOKIE_PATH
            )

    def clear_auth_cookies(self, response: Response) -> None:
        """Clear all authentication cookies."""
        cookie_names = ["access_token", "refresh_token", "auth_session", "csrf_token"]

        for cookie_name in cookie_names:
            response.delete_cookie(
                key=cookie_name,
                domain=settings.COOKIE_DOMAIN,
                path=settings.COOKIE_PATH,
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAMESITE  # Use configured value directly
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
    
    async def extract_refresh_token_from_request(self, request: Request, skip_body: bool = False) -> Optional[str]:
        """Extract refresh token from cookies, header, or JSON body (fallback).

        Args:
            request: The FastAPI request
            skip_body: If True, don't try to read from request body (prevents consuming body before endpoint)
        """

        # Try cookies first
        token = request.cookies.get("refresh_token")
        if token:
            return token

        # Fallback to custom header
        header_token = request.headers.get("X-Refresh-Token")
        if header_token:
            return header_token

        # Final fallback: JSON body (only if not skipping and on refresh endpoint)
        # IMPORTANT: Don't read body in middleware for non-refresh endpoints
        # as it consumes the body and prevents endpoints from reading it
        if not skip_body:
            try:
                # Only read body for explicit refresh endpoints
                path = request.url.path
                if request.method in ("POST", "PUT") and "refresh" in path:
                    content_type = request.headers.get("content-type", "").lower()
                    if "application/json" in content_type:
                        data = await request.json()
                        body_token = data.get("refresh_token") if isinstance(data, dict) else None
                        if body_token:
                            return body_token
            except Exception:
                # Ignore body parsing errors
                pass

        return None
    
    async def verify_and_refresh_if_needed(
        self,
        request: Request,
        response: Response,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Verify token and automatically refresh if needed with sliding session support."""

        access_token = self.extract_token_from_request(request)
        if not access_token:
            # No access token, but check if there's a refresh token
            # This handles cases where old cookies expired before sliding session was deployed
            # IMPORTANT: skip_body=True to avoid consuming request body before endpoints can read it
            refresh_token = await self.extract_refresh_token_from_request(request, skip_body=True)
            if refresh_token:
                logger.info("No access token found, but refresh token exists - attempting token refresh")
                return await self.refresh_token_flow(request, response, db, sliding_refresh=True)
            return None

        # Check for test tokens first (development/testing)
        from app.core.auth import VALID_TEST_TOKENS
        if settings.is_development() and access_token in VALID_TEST_TOKENS:
            return {
                "user_id": 999999,
                "sub": "test@example.com",
                "type": "access",
                "test_token": True
            }

        try:
            # Verify access token
            # Verify token; support RS256 when configured
            algorithms = [getattr(settings, "JWT_SIGNING_ALG", settings.ALGORITHM)]
            key = settings.SECRET_KEY
            if algorithms[0].upper() == "RS256" and settings.JWT_PUBLIC_KEY:
                key = settings.JWT_PUBLIC_KEY

            payload = jwt.decode(access_token, key, algorithms=algorithms)

            # Check if token is blacklisted
            if await TokenBlacklist.is_blacklisted(db, access_token):
                return None

            # SLIDING SESSION: Check absolute session age (60-day maximum)
            if settings.SLIDING_SESSION_ENABLED:
                session_started_at = payload.get("session_started_at")
                if session_started_at:
                    from datetime import timezone
                    session_start = datetime.fromtimestamp(session_started_at, tz=timezone.utc)
                    current_time = datetime.now(timezone.utc)
                    session_age = current_time - session_start
                    max_session_age = timedelta(days=settings.SLIDING_SESSION_ABSOLUTE_MAX_DAYS)

                    if session_age > max_session_age:
                        logger.info(f"Session exceeded absolute maximum of {settings.SLIDING_SESSION_ABSOLUTE_MAX_DAYS} days, forcing logout")
                        return None

                # SLIDING SESSION: Check if cookies need refresh (24-hour interval)
                cookie_issued_at = payload.get("cookie_issued_at")
                if cookie_issued_at:
                    cookie_age_hours = (datetime.now(timezone.utc) - datetime.fromtimestamp(cookie_issued_at, tz=timezone.utc)).total_seconds() / 3600
                    if cookie_age_hours > settings.SLIDING_SESSION_REFRESH_HOURS:
                        logger.info(f"Cookies are {cookie_age_hours:.1f} hours old, triggering sliding session refresh")
                        return await self.refresh_token_flow(request, response, db, sliding_refresh=True)

            # Check if token expires soon and auto-refresh is enabled
            if settings.AUTO_REFRESH_ENABLED:
                exp_timestamp = payload.get("exp")
                if exp_timestamp:
                    # Use timezone-aware datetime for correct comparison
                    from datetime import timezone
                    exp_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
                    current_time = datetime.now(timezone.utc)
                    time_until_expiry = exp_time - current_time

                    logger.debug(f"Token expires in {time_until_expiry.total_seconds()/60:.1f} minutes (threshold: {settings.AUTO_REFRESH_THRESHOLD_MINUTES} min)")

                    # If token expires within threshold, refresh automatically
                    if time_until_expiry < timedelta(minutes=settings.AUTO_REFRESH_THRESHOLD_MINUTES):
                        logger.info(f"Token expires soon ({time_until_expiry.total_seconds()/60:.1f} min), triggering auto-refresh")
                        return await self.refresh_token_flow(request, response, db)

            return payload

        except jwt.ExpiredSignatureError:
            # Token expired, try to refresh
            return await self.refresh_token_flow(request, response, db)
        except JWTError:
            return None
    
    async def refresh_token_flow(
        self,
        request: Request,
        response: Response,
        db: AsyncSession,
        sliding_refresh: bool = False,
        skip_body: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Handle token refresh flow with sliding session support.

        Args:
            request: The current request
            response: The response to set cookies on
            db: Database session
            sliding_refresh: If True, preserve original session_started_at for sliding sessions
            skip_body: If True, don't read request body (default True to avoid consuming body in middleware)
        """

        # IMPORTANT: When called from middleware, skip_body should be True to avoid
        # consuming the request body before endpoints can read it
        refresh_token = await self.extract_refresh_token_from_request(request, skip_body=skip_body)
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

            # For sliding sessions, preserve the original session start time
            session_started_at = None
            if sliding_refresh and settings.SLIDING_SESSION_ENABLED:
                session_started_timestamp = payload.get("session_started_at")
                if session_started_timestamp:
                    from datetime import timezone
                    session_started_at = datetime.fromtimestamp(session_started_timestamp, tz=timezone.utc)
                    logger.info(f"Preserving session start time for sliding refresh: {session_started_at}")

            # Create new tokens
            remember_me = payload.get("remember_me", False)
            new_tokens = self.create_session_tokens(user, remember_me, session_started_at=session_started_at)

            # Set new cookies
            self.set_auth_cookies(response, new_tokens)

            # Expose refreshed tokens for downstream handlers (optional JSON return)
            try:
                setattr(request.state, "refreshed_tokens", new_tokens)
            except Exception:
                pass

            # Blacklist old refresh token
            exp_time = datetime.fromtimestamp(payload["exp"])
            await TokenBlacklist.add_token(db, refresh_token, exp_time)

            # Return new access token payload
            algorithms = [getattr(settings, "JWT_SIGNING_ALG", settings.ALGORITHM)]
            key = settings.SECRET_KEY
            if algorithms[0].upper() == "RS256" and settings.JWT_PUBLIC_KEY:
                key = settings.JWT_PUBLIC_KEY
            new_payload = jwt.decode(new_tokens["access_token"], key, algorithms=algorithms)
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