from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict

from fastapi import APIRouter, Request, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from pydantic import BaseModel, Field, validator
from sqlalchemy import select

from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    log_security_event,
)
from app.core.auth import get_current_user, oauth2_scheme, AuthenticationManager  # Import centralized oauth2_scheme
from app.db.database import get_db
from app.db.models import User
from app.db.models import TokenBlacklist
from app.schemas.token import TokenResponse
from app.schemas.google_auth import GoogleAuthRequest, GoogleAuthResponse, UserResponse
from app.schemas.user import ChangePasswordRequest, ChangePasswordResponse, ChangeUsernameRequest, ChangeUsernameResponse
from app.services.google_oauth import GoogleOAuthService, GoogleTokenValidationError
# from app.services.journal_service import JournalService  # Temporarily disabled
from app.core.config import settings
from app.core.enhanced_auth import enhanced_auth_service
from app.utils.security import get_client_ip
from app.core.security_config import security_config
from app.utils.rate_limiter import apply_auth_rate_limit
import logging

logger = logging.getLogger("auth_endpoints")

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1, max_length=200)
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None

    @validator('email')
    def validate_email(cls, v):
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower().strip()

    @validator('password')
    def validate_password(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Password is required')
        return v.strip()


class EnhancedLoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1, max_length=200)
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None
    remember_me: bool = False

    @validator('email')
    def validate_email(cls, v):
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower().strip()

    @validator('password')
    def validate_password(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Password is required')
        return v.strip()


class EnhancedTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    remember_me: bool = False
    user: Optional[Dict[str, Any]] = None


class RegisterSchema(BaseModel):
    email: str  # Changed from EmailStr to avoid DNS lookups
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field(..., min_length=1, max_length=100)

    @validator('email')
    def validate_email(cls, v):
        import re
        # Simple regex validation without DNS lookup
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower().strip()

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Name is required')
        return v.strip()

class FastRegisterSchema(BaseModel):
    """Simplified registration schema without EmailStr validation that might hang"""
    email: str  # Regular string instead of EmailStr
    password: str
    name: str


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User:
    """Authenticate user with email and password."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        log_security_event(
            event_type="login_failed",
            details={"email": email, "reason": "invalid_credentials"},
            level="warning"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/login", response_model=EnhancedTokenResponse)
async def enhanced_login(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced login with cookies and remember me functionality."""
    try:
        # Apply rate limiting for login attempts
        await apply_auth_rate_limit(request, "login")

        content_type = request.headers.get("content-type", "")
        # Basic brute-force protection: check recent attempts and lockout
        ip_addr = get_client_ip(request)
        creds = None

        if "application/json" in content_type:
            data = await request.json()
            creds = EnhancedLoginRequest(**data)

            if settings.AUTH_REQUIRE_GRANT_TYPE and creds.grant_type != settings.AUTH_DEFAULT_GRANT_TYPE:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid grant_type, must be '{settings.AUTH_DEFAULT_GRANT_TYPE}'",
                )

            # Pre-check lockout window if user exists
            pre_user = None
            try:
                result = await db.execute(select(User).where(User.email == creds.email))
                pre_user = result.scalar_one_or_none()

                if pre_user:
                    if pre_user.locked_until and pre_user.locked_until > datetime.now(timezone.utc):
                        retry_after = int((pre_user.locked_until - datetime.now(timezone.utc)).total_seconds())
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Account temporarily locked due to multiple failed attempts",
                            headers={"Retry-After": str(max(1, retry_after))}
                        )
            except HTTPException:
                raise
            except Exception:
                pre_user = None

            try:
                user = await authenticate_user(creds.email, creds.password, db)

            except HTTPException as e:
                # Record failed attempt and lock if needed
                try:
                    from app.db.models import LoginAttempt
                    if pre_user:
                        await LoginAttempt.record_attempt(db, pre_user.id, False, ip_addr)
                        attempts = await LoginAttempt.get_recent_attempts(db, pre_user.id, security_config.LOCKOUT_PERIOD_MINUTES)
                        failed_recent = sum(1 for a in attempts if not a.success)
                        if failed_recent >= security_config.MAX_FAILED_LOGIN_ATTEMPTS:
                            pre_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=security_config.LOCKOUT_DURATION_MINUTES)
                            await db.commit()
                except Exception:
                    pass
                raise e

            # Record successful attempt
            try:
                from app.db.models import LoginAttempt
                await LoginAttempt.record_attempt(db, user.id, True, ip_addr)
            except Exception:
                pass

            # Create session tokens with remember me
            tokens = enhanced_auth_service.create_session_tokens(user, creds.remember_me)

            # Set auth cookies
            enhanced_auth_service.set_auth_cookies(response, tokens)

            # Log successful login
            log_security_event(
                event_type="login_success",
                details={
                    "email": user.email,
                    "user_id": user.id,
                    "remember_me": creds.remember_me,
                    "session_id": "cookie_based"
                },
                level="info"
            )

            return EnhancedTokenResponse(
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_type="bearer",
                expires_in=tokens["expires_in"],
                remember_me=creds.remember_me,
                user={
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "profile_picture": user.profile_picture
                }
            )

        elif "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            grant = form.get("grant_type", settings.AUTH_DEFAULT_GRANT_TYPE)

            if settings.AUTH_REQUIRE_GRANT_TYPE and grant != settings.AUTH_DEFAULT_GRANT_TYPE:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid grant_type, must be '{settings.AUTH_DEFAULT_GRANT_TYPE}'",
                )

            email = form.get("username") or form.get("email")
            if not email:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Email is required"
                )

            remember_me = form.get("remember_me", "").lower() in ("true", "1", "yes")
            # Pre-check lockout window if user exists
            pre_user = None
            try:
                result = await db.execute(select(User).where(User.email == email))
                pre_user = result.scalar_one_or_none()
                if pre_user and pre_user.locked_until and pre_user.locked_until > datetime.now(timezone.utc):
                    retry_after = int((pre_user.locked_until - datetime.now(timezone.utc)).total_seconds())
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Account temporarily locked due to multiple failed attempts",
                        headers={"Retry-After": str(max(1, retry_after))}
                    )
            except HTTPException:
                raise
            except Exception:
                pre_user = None

            try:
                user = await authenticate_user(email, form["password"], db)
            except HTTPException as e:
                # Record failed attempt and lock if needed
                try:
                    from app.db.models import LoginAttempt
                    if pre_user:
                        await LoginAttempt.record_attempt(db, pre_user.id, False, ip_addr)
                        attempts = await LoginAttempt.get_recent_attempts(db, pre_user.id, security_config.LOCKOUT_PERIOD_MINUTES)
                        failed_recent = sum(1 for a in attempts if not a.success)
                        if failed_recent >= security_config.MAX_FAILED_LOGIN_ATTEMPTS:
                            pre_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=security_config.LOCKOUT_DURATION_MINUTES)
                            await db.commit()
                except Exception:
                    pass
                raise e
            # Record successful attempt
            try:
                from app.db.models import LoginAttempt
                await LoginAttempt.record_attempt(db, user.id, True, ip_addr)
            except Exception:
                pass

            # Create session tokens
            tokens = enhanced_auth_service.create_session_tokens(user, remember_me)

            # Set auth cookies
            enhanced_auth_service.set_auth_cookies(response, tokens)

            # Log successful login
            log_security_event(
                event_type="login_success",
                details={
                    "email": user.email,
                    "user_id": user.id,
                    "remember_me": remember_me
                },
                level="info"
            )

            return EnhancedTokenResponse(
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_type="bearer",
                expires_in=tokens["expires_in"],
                remember_me=remember_me,
                user={
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "profile_picture": user.profile_picture
                }
            )

        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported Media Type",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        logger.exception("Login exception details:")
        raise


@router.post("/logout")
async def enhanced_logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced logout with cookie clearing and token blacklisting."""

    # Get current user if authenticated
    user = None
    try:
        user = await get_current_user(request, db)
    except:
        pass  # Not authenticated, proceed with logout anyway

    # Extract tokens from cookies for blacklisting
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    # Blacklist tokens if they exist
    if access_token:
        try:
            # Decode token to get expiration
            payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            exp = payload.get("exp")
            if exp:
                token_blacklist = TokenBlacklist(
                    jti=payload.get("jti", "unknown"),
                    token_type="access",
                    expires_at=datetime.fromtimestamp(exp, tz=timezone.utc)
                )
                db.add(token_blacklist)
        except JWTError:
            pass  # Invalid token, ignore

    if refresh_token:
        try:
            # Decode token to get expiration
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            exp = payload.get("exp")
            if exp:
                token_blacklist = TokenBlacklist(
                    jti=payload.get("jti", "unknown"),
                    token_type="refresh",
                    expires_at=datetime.fromtimestamp(exp, tz=timezone.utc)
                )
                db.add(token_blacklist)
        except JWTError:
            pass  # Invalid token, ignore

    await db.commit()

    # Clear auth cookies
    enhanced_auth_service.clear_auth_cookies(response)

    # Log logout event
    log_security_event(
        event_type="logout",
        details={"user_id": user.id if user else None, "session_type": "cookie_based"},
        level="info",
        user_id=user.id if user else None
    )

    return {"message": "Successfully logged out"}


@router.post("/refresh", response_model=TokenResponse)
async def enhanced_refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced token refresh with cookie support."""

    # Try to get refresh token from cookies first, then from body
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        # Fallback to JSON body for API clients
        try:
            body = await request.json()
            refresh_token = body.get("refresh_token")
        except:
            pass

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Validate refresh token
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")

        if email is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti:
            result = await db.execute(
                select(TokenBlacklist).where(
                    TokenBlacklist.jti == jti,
                    TokenBlacklist.token_type == "refresh"
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new tokens
    tokens = enhanced_auth_service.create_session_tokens(user, remember_me=True)

    # Update cookies
    enhanced_auth_service.set_auth_cookies(response, tokens)

    # Blacklist old refresh token
    if jti:
        try:
            old_token_blacklist = TokenBlacklist(
                jti=jti,
                token_type="refresh",
                expires_at=datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)
            )
            db.add(old_token_blacklist)
            await db.commit()
        except Exception:
            pass  # Don't fail refresh if blacklisting fails

    # Log refresh event
    log_security_event(
        event_type="token_refresh",
        details={"user_id": user.id, "session_type": "cookie_based"},
        level="info",
        user_id=user.id
    )

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_in=tokens["expires_in"]
    )


@router.post("/refresh-token", response_model=TokenResponse)
async def enhanced_refresh_token_alias(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Alias for clients calling /auth/refresh-token; delegates to refresh."""
    return await enhanced_refresh_token(request, response, db)


# Removed duplicate basic /login route - using enhanced_login() above which has:
# - Cookie-based authentication with remember me
# - Comprehensive timing and performance logging
# - Brute-force protection with account lockout
# - Better error handling and security event tracking

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterSchema,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Register new user with email and password - Enhanced with rate limiting"""
    import asyncio

    user_email = data.email
    client_ip = get_client_ip(request)

    try:
        # Apply rate limiting for registration (3 attempts per hour)
        await apply_auth_rate_limit(request, "register")

        # Check if user already exists with timeout
        try:
            result = await asyncio.wait_for(
                db.execute(select(User).where(User.email == data.email)),
                timeout=5.0
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable. Please try again."
            )

        # Hash password
        hashed_password = get_password_hash(data.password)

        # Create new user with timeout
        try:
            user = User(
                email=data.email,
                name=data.name,
                hashed_password=hashed_password,
                auth_provider="email",
                is_active=True
            )
            db.add(user)
            await asyncio.wait_for(db.commit(), timeout=5.0)
            await asyncio.wait_for(db.refresh(user), timeout=5.0)

        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable. Please try again."
            )

        # Create tokens - using enhanced_auth_service for consistency
        tokens = enhanced_auth_service.create_session_tokens(user, remember_me=False)

        # Set auth cookies for session persistence
        enhanced_auth_service.set_auth_cookies(response, tokens)

        log_security_event(
            event_type="registration_success",
            details={
                "email": user.email,
                "user_id": user.id,
                "client_ip": client_ip
            },
            level="info",
            user_id=user.id
        )

        return {
            "message": "Registration successful",
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "success": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed for {user_email}: {str(e)}")
        logger.exception("Registration exception details:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )




@router.post("/google", response_model=GoogleAuthResponse)
async def google_auth(
    raw_request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authenticate user with Google OAuth ID token.

    This endpoint:
    1. Verifies the Google ID token using secure validation
    2. Creates a new user if they don't exist
    3. Returns a JWT access token for API access
    """
    import json

    try:
        # Parse JSON body - use cached body from middleware if available
        try:
            # Check if middleware already cached the body
            if hasattr(raw_request.state, 'cached_body'):
                body = raw_request.state.cached_body
                logger.info("🔐 GOOGLE AUTH: Using cached body from middleware")
            else:
                body = await raw_request.body()
                logger.info("🔐 GOOGLE AUTH: Reading body directly (no cache)")

            body_str = body.decode('utf-8')
            logger.info(f"🔐 GOOGLE AUTH RAW BODY: {body_str[:200]}")

            # Parse the already-read body
            request_data = json.loads(body_str)
            logger.info(f"🔐 GOOGLE AUTH PARSED JSON: {list(request_data.keys())}")
            request = GoogleAuthRequest(**request_data)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON format: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request format: {str(e)}"
            )

        google_service = GoogleOAuthService()

        # Verify Google token and extract user info with enhanced security validation
        user_info = await google_service.verify_token(request.id_token)

        # Check if email is verified
        if not user_info.get('email_verified', False):
            log_security_event(
                event_type="google_auth_failed",
                details={"reason": "email_not_verified", "email": user_info['email']},
                level="warning"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified"
            )

        # Check if user exists by Google ID first
        result = await db.execute(
            select(User).where(User.google_id == user_info['google_id'])
        )
        user = result.scalar_one_or_none()

        # If not found by Google ID, check by email
        if not user:
            result = await db.execute(
                select(User).where(User.email == user_info['email'])
            )
            user = result.scalar_one_or_none()

            # If found by email, update with Google ID (link accounts)
            if user:
                user.google_id = user_info['google_id']
                user.auth_provider = "google"
                user.profile_picture = user_info.get('picture')
                if not user.name and user_info.get('name'):
                    user.name = user_info['name']

                await db.commit()
                await db.refresh(user)

                log_security_event(
                    event_type="account_linked",
                    details={"email": user.email, "provider": "google"},
                    level="info",
                    user_id=user.id
                )

        # If user doesn't exist, create new one
        if not user:
            # Get existing emails to ensure uniqueness
            email_check = await db.execute(select(User).where(User.email == user_info['email']))
            if email_check.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email address is already registered with a different account"
                )

            user = User(
                email=user_info['email'],
                google_id=user_info['google_id'],
                name=user_info.get('name', 'Google User'),
                profile_picture=user_info.get('picture'),
                auth_provider="google",
                is_active=True
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            log_security_event(
                event_type="google_registration_success",
                details={"email": user.email, "user_id": user.id, "google_id": user_info['google_id']},
                level="info",
                user_id=user.id
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )

        # Create session tokens with cookies (like regular login)
        tokens = enhanced_auth_service.create_session_tokens(user, remember_me=True)

        # Set auth cookies for session persistence
        enhanced_auth_service.set_auth_cookies(response, tokens)

        log_security_event(
            event_type="google_login_success",
            details={"email": user.email, "user_id": user.id},
            level="info",
            user_id=user.id
        )

        return GoogleAuthResponse(
            access_token=tokens["access_token"],
            token_type="bearer",
            expires_in=tokens["expires_in"],
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                profile_picture=user.profile_picture,
                auth_provider=user.auth_provider,
                is_active=user.is_active
            )
        )

    except HTTPException:
        raise
    except GoogleTokenValidationError as e:
        log_security_event(
            event_type="google_auth_failed",
            details={"reason": "token_validation_error", "error": str(e)},
            level="warning"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )
    except Exception as e:
        logger.error(f"Google authentication failed: {str(e)}")
        logger.exception("Google OAuth exception details:")
        log_security_event(
            event_type="google_auth_error",
            details={"error": str(e), "error_type": type(e).__name__},
            level="error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google authentication failed"
        )


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password with current password verification."""

    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        log_security_event(
            event_type="password_change_failed",
            details={"user_id": current_user.id, "reason": "invalid_current_password"},
            level="warning",
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Hash new password
    new_hashed_password = get_password_hash(request.new_password)

    # Update password in database
    current_user.hashed_password = new_hashed_password
    await db.commit()

    log_security_event(
        event_type="password_change_success",
        details={"user_id": current_user.id},
        level="info",
        user_id=current_user.id
    )

    return ChangePasswordResponse(message="Password changed successfully")


@router.post("/change-username", response_model=ChangeUsernameResponse)
async def change_username(
    request: ChangeUsernameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change username with validation."""

    # Check if username already exists
    result = await db.execute(select(User).where(User.name == request.new_username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # Update username
    old_username = current_user.name
    current_user.name = request.new_username
    await db.commit()

    log_security_event(
        event_type="username_change",
        details={"user_id": current_user.id, "old_username": old_username, "new_username": request.new_username},
        level="info",
        user_id=current_user.id
    )

    return ChangeUsernameResponse(
        message="Username changed successfully",
        new_username=request.new_username
    )


@router.get("/cookie-support")
async def cookie_support():
    """Check if cookies are supported - required for Google OAuth."""
    return {
        "cookies_supported": True,
        "message": "Cookies are supported for authentication"
    }


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Get current authenticated user information."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "profile_picture": current_user.profile_picture,
        "is_active": current_user.is_active,
        "auth_provider": current_user.auth_provider,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }