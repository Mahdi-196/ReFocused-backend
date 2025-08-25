from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict

from fastapi import APIRouter, Request, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field, validator
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
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Password is required')
        return v.strip()


class RegisterSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)
    name: Optional[str] = Field(None, max_length=100)

    @validator('password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        if not any(c in '!@#$%^&*()_+-=[]{};\':"|,.<>/?~`' for c in v):
            raise ValueError('Password must contain at least one special character')
        return v

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            import re
            # Remove HTML tags
            cleaned = re.sub(r'<[^>]*>', '', v)
            if len(cleaned.strip()) == 0:
                return None
            if len(cleaned) > 100:
                raise ValueError('Name is too long (max 100 characters)')
            return cleaned.strip()
        return v


class UserProfile(BaseModel):
    """User profile response."""
    id: int
    email: str
    name: str
    profile_picture: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    member_since: Optional[str] = None

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    profile_picture: Optional[str] = Field(None, max_length=500)
    avatar: Optional[str] = Field(None, max_length=500)  # Legacy support for frontend compatibility

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            import re
            # Remove HTML tags for security
            cleaned = re.sub(r'<[^>]*>', '', v)
            if len(cleaned.strip()) == 0:
                return None
            if len(cleaned) > 100:
                raise ValueError('Name is too long (max 100 characters)')
            return cleaned.strip()
        return v

    @validator('profile_picture', 'avatar')
    def validate_image_url(cls, v):
        if v is not None:
            import re
            # Basic URL validation and XSS prevention
            if not re.match(r'^https?://[^\s<>"]{1,500}$', v):
                raise ValueError('Invalid image URL format')
            # Block javascript: and data: URLs for security
            if v.lower().startswith(('javascript:', 'data:')):
                raise ValueError('Invalid image URL - security risk detected')
        return v


class EnhancedLoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None


class EnhancedTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    remember_me: bool = False
    user: Optional[Dict[str, Any]] = None


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User:
    """Authenticate user by email and password."""
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
    
    # Apply rate limiting for login attempts
    await apply_auth_rate_limit(request, "login")
    
    content_type = request.headers.get("content-type", "")
    # Basic brute-force protection: check recent attempts and lockout
    ip_addr = get_client_ip(request)
    
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


@router.post("/logout")
async def enhanced_logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced logout with cookie clearing and token blacklisting."""
    
    try:
        # Try to get token from cookies first, then header
        access_token = enhanced_auth_service.extract_token_from_request(request)
        refresh_token = enhanced_auth_service.extract_refresh_token_from_request(request)
        
        user_id = None
        
        # Blacklist access token if present
        if access_token:
            try:
                algorithms = [getattr(settings, "JWT_SIGNING_ALG", settings.ALGORITHM)]
                key = settings.SECRET_KEY
                if algorithms[0].upper() == "RS256" and settings.JWT_PUBLIC_KEY:
                    key = settings.JWT_PUBLIC_KEY
                payload = jwt.decode(access_token, key, algorithms=algorithms)
                expires_at = datetime.fromtimestamp(payload["exp"])
                await TokenBlacklist.add_token(db, access_token, expires_at)
                user_id = payload.get("sub")
            except JWTError:
                pass  # Token already invalid
        
        # Blacklist refresh token if present
        if refresh_token:
            try:
                algorithms = [getattr(settings, "JWT_SIGNING_ALG", settings.ALGORITHM)]
                key = settings.SECRET_KEY
                if algorithms[0].upper() == "RS256" and settings.JWT_PUBLIC_KEY:
                    key = settings.JWT_PUBLIC_KEY
                payload = jwt.decode(refresh_token, key, algorithms=algorithms)
                expires_at = datetime.fromtimestamp(payload["exp"])
                await TokenBlacklist.add_token(db, refresh_token, expires_at)
                if not user_id:
                    user_id = payload.get("sub")
            except JWTError:
                pass  # Token already invalid
        
        # Clear auth cookies
        enhanced_auth_service.clear_auth_cookies(response)
        
        # Log successful logout
        if user_id:
            log_security_event(
                event_type="logout_success",
                details={"user_id": user_id},
                level="info"
            )
        
        return {
            "message": "Successfully logged out",
            "redirect_url": "/"
        }
        
    except Exception as e:
        # Even if there's an error, clear cookies and return success
        enhanced_auth_service.clear_auth_cookies(response)
        logger.warning(f"Logout error (still clearing cookies): {str(e)}")
        
        return {
            "message": "Logged out", 
            "redirect_url": "/"
        }


@router.post("/refresh", response_model=EnhancedTokenResponse)
async def enhanced_refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced token refresh with automatic cookie management."""
    
    payload = await enhanced_auth_service.refresh_token_flow(request, response, db)
    
    if not payload:
        # Clear invalid cookies
        enhanced_auth_service.clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Get user info for response
    try:
        # Access token payload contains both 'sub' (email) and 'user_id'
        user_id = payload.get("user_id")
        if isinstance(user_id, str):
            user_id = int(user_id) if user_id.isdigit() else None
        if not isinstance(user_id, int):
            raise ValueError("user_id missing in token payload")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # If tokens were refreshed in this request, include access token in JSON
        access_token_value = "set_in_cookie"
        refresh_token_value = "set_in_cookie"
        if hasattr(request.state, "refreshed_tokens"):
            tokens = getattr(request.state, "refreshed_tokens") or {}
            access_token_value = tokens.get("access_token", access_token_value)
            refresh_token_value = tokens.get("refresh_token", refresh_token_value)

        return EnhancedTokenResponse(
            access_token=access_token_value,
            refresh_token=refresh_token_value,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            remember_me=payload.get("remember_me", False),
            user={
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "profile_picture": user.profile_picture
            }
        )
        
    except (ValueError, TypeError):
        enhanced_auth_service.clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )


@router.post("/refresh-token", response_model=EnhancedTokenResponse)
async def enhanced_refresh_token_alias(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Alias for clients calling /auth/refresh-token; delegates to refresh."""
    return await enhanced_refresh_token(request, response, db)

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterSchema, response: Response, request: Request, db: AsyncSession = Depends(get_db)) -> Any:
    # Apply rate limiting for registration attempts
    await apply_auth_rate_limit(request, "register")
    
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    # Check if email was recently deleted (within 72 hours)
    from app.db.models import DeletedEmail
    deleted_check = await DeletedEmail.is_email_recently_deleted(db, data.email)
    if deleted_check["is_deleted"]:
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "email_recently_deleted",
                "message": f"This email address cannot be used to create a new account. Please try again in {deleted_check['hours_remaining']} hours.",
                "hours_remaining": deleted_check["hours_remaining"],
                "available_at": deleted_check["available_at"]
            }
        )
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        name=data.name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Set up default journal collection for new user
                # await JournalService.setup_user_journal_async(db, user.id)  # Temporarily disabled
    
    # Log successful registration
    log_security_event(
        event_type="registration_success",
        details={"email": user.email, "user_id": user.id},
        level="info"
    )
    
    # Create session tokens and set cookies for immediate login
    tokens = enhanced_auth_service.create_session_tokens(user, remember_me=False)
    enhanced_auth_service.set_auth_cookies(response, tokens)
    
    return {
        "message": "User created successfully",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": tokens["expires_in"]
    }


@router.post("/google", response_model=GoogleAuthResponse)
async def google_auth(
    request: GoogleAuthRequest,
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
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Google OAuth request received with token length: {len(request.id_token)}")
        
        google_service = GoogleOAuthService()
        
        # Verify Google token and extract user info with enhanced security validation
        logger.info("Attempting to verify Google token...")
        user_info = await google_service.verify_token(request.id_token)
        
        logger.info(f"Google token verified successfully for email: {user_info.get('email')}")
        
        # Check if email is verified
        if not user_info.get('email_verified', False):
            logger.warning(f"Email not verified for user: {user_info['email']}")
            log_security_event(
                event_type="google_auth_failed",
                details={"reason": "email_not_verified", "email": user_info['email']},
                level="warning"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified"
            )
        
        logger.info("Starting database operations...")
        
        # Check if user exists by Google ID first
        logger.info(f"Checking for existing user with Google ID: {user_info['google_id']}")
        result = await db.execute(
            select(User).where(User.google_id == user_info['google_id'])
        )
        user = result.scalar_one_or_none()
        
        # If not found by Google ID, check by email
        if not user:
            logger.info(f"No user found with Google ID, checking by email: {user_info['email']}")
            result = await db.execute(
                select(User).where(User.email == user_info['email'])
            )
            user = result.scalar_one_or_none()
            
            # If found by email, update with Google ID (link accounts)
            if user:
                logger.info(f"Found existing user by email, linking Google account: {user.email}")
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
            logger.info("Creating new user from Google OAuth data")
            
            # Get existing emails to ensure uniqueness
            result = await db.execute(select(User.email))
            existing_emails = {row[0] for row in result.fetchall()}
            
            # Generate email from Google
            base_email = google_service.extract_email_from_user_info(user_info)
            unique_email = google_service.generate_unique_email(base_email, existing_emails)
            
            logger.info(f"Generated unique email: {unique_email}")
            
            # Check if the generated email was recently deleted (within 72 hours)
            from app.db.models import DeletedEmail
            deleted_check = await DeletedEmail.is_email_recently_deleted(db, unique_email)
            if deleted_check["is_deleted"]:
                raise HTTPException(
                    status_code=400, 
                    detail={
                        "error": "email_recently_deleted",
                        "message": f"This email address cannot be used to create a new account. Please try again in {deleted_check['hours_remaining']} hours.",
                        "hours_remaining": deleted_check["hours_remaining"],
                        "available_at": deleted_check["available_at"]
                    }
                )
            
            # Create new user
            user = User(
                email=unique_email,
                hashed_password=None,  # No password for Google OAuth users
                name=user_info.get('name', ''),
                google_id=user_info['google_id'],
                profile_picture=user_info.get('picture'),
                auth_provider="google",
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            # Set up default journal collection for new user
            # await JournalService.setup_user_journal_async(db, user.id)  # Temporarily disabled
            
            logger.info(f"New user created successfully: {user.email} (ID: {user.id})")
            
            log_security_event(
                event_type="user_created",
                details={"email": user.email, "provider": "google"},
                level="info",
                user_id=user.id
            )
        
        logger.info("Generating session tokens and setting cookies...")
        
        # Use enhanced auth service to create session tokens and set cookies
        tokens = enhanced_auth_service.create_session_tokens(user, remember_me=True)
        enhanced_auth_service.set_auth_cookies(response, tokens)
        
        # Log successful authentication
        log_security_event(
            event_type="google_auth_success",
            details={"email": user.email},
            level="info",
            user_id=user.id
        )
        
        # Prepare user response
        user_response = UserResponse(
            id=user.id,
            email=user.email,
            name=user.name or user.email,
            username=user.email,
            profile_picture=user.profile_picture
        )
        
        logger.info(f"Google OAuth authentication successful for user: {user.email}")
        
        return GoogleAuthResponse(
            access_token=tokens["access_token"],
            user=user_response,
            token_type="bearer",
            expires_in=tokens["expires_in"]
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Handle Google token validation errors specifically
        if isinstance(e, GoogleTokenValidationError):
            logger.warning(f"Google token validation failed: {str(e)}")
            log_security_event(
                event_type="google_auth_failed",
                details={"reason": "token_validation_failed", "error": str(e)},
                level="warning"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Google token: {str(e)}"
            )
        
        # Handle other unexpected errors
        logger.error(f"Unexpected error in Google OAuth: {str(e)}", exc_info=True)
        await db.rollback()
        log_security_event(
            event_type="google_auth_error",
            details={"error": str(e), "error_type": type(e).__name__},
            level="error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to server error"
        )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
) -> UserProfile:
    """Get current user profile information."""
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture=current_user.profile_picture,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
        member_since=current_user.created_at.isoformat() if current_user.created_at else None
    )


@router.put("/profile", response_model=UserProfile)
async def update_user_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """Update current user profile information."""
    
    # Update user fields
    if profile_data.name is not None:
        current_user.name = profile_data.name
    
    # Handle both profile_picture and avatar fields (for frontend compatibility)
    avatar_url = None
    if profile_data.profile_picture is not None:
        avatar_url = profile_data.profile_picture
    elif profile_data.avatar is not None:
        avatar_url = profile_data.avatar
    
    if avatar_url is not None:
        current_user.profile_picture = avatar_url
    
    await db.commit()
    await db.refresh(current_user)
    
    # Log profile update
    updated_fields = []
    if profile_data.name is not None:
        updated_fields.append("name")
    if avatar_url is not None:
        updated_fields.append("profile_picture")
        
    log_security_event(
        event_type="profile_update",
        details={"updated_fields": updated_fields},
        level="info",
        user_id=current_user.id
    )
    
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture=current_user.profile_picture,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
        member_since=current_user.created_at.isoformat() if current_user.created_at else None
    )


@router.post("/test-login", response_model=TokenResponse)
async def test_login() -> TokenResponse:
    """
    Quick test login endpoint for development - returns a valid test token.
    This eliminates the need for real authentication during frontend testing.
    """
    if not settings.is_development():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not available in production"
        )
    
    # Return the same test token that the backend recognizes
    return TokenResponse(
        access_token="test-token-for-cache-testing",
        refresh_token="test-token-for-cache-testing",
        token_type="bearer",
        expires_in=86400,  # 24 hours
        scope=""
    )


@router.get("/status", response_model=Dict[str, Any])
async def auth_status(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Check current authentication status with automatic refresh."""
    
    try:
        # Use enhanced auth service to check/refresh authentication
        user = await enhanced_auth_service.get_current_user_from_request(request, response, db)
        
        if user:
            return {
                "authenticated": True,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "profile_picture": user.profile_picture,
                    "created_at": user.created_at.isoformat() if user.created_at else None
                },
                "session_info": {
                    "has_access_token": bool(request.cookies.get("access_token")),
                    "has_refresh_token": bool(request.cookies.get("refresh_token")),
                    "has_session": bool(request.cookies.get("auth_session"))
                }
            }
        else:
            return {
                "authenticated": False,
                "user": None,
                "session_info": {
                    "has_access_token": False,
                    "has_refresh_token": False,
                    "has_session": False
                },
                "redirect_url": "/"
            }
            
    except Exception as e:
        logger.error(f"Auth status check error: {str(e)}")
        return {
            "authenticated": False,
            "user": None,
            "error": "Authentication check failed",
            "redirect_url": "/"
        }


@router.put("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ChangePasswordResponse:
    """
    Change user password with security validation.
    
    Requires current password verification and validates new password strength.
    Only works for users with password-based authentication (not OAuth users).
    """
    
    # Check if user has a password (not OAuth-only user)
    if not current_user.hashed_password:
        log_security_event(
            event_type="password_change_failed",
            details={"reason": "oauth_user_no_password", "user_id": current_user.id},
            level="warning",
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change not available for OAuth-only accounts"
        )
    
    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        log_security_event(
            event_type="password_change_failed",
            details={"reason": "invalid_current_password", "user_id": current_user.id},
            level="warning",
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Validate new password strength (basic validation)
    if len(request.new_password) < 8:
        log_security_event(
            event_type="password_change_failed",
            details={"reason": "weak_password", "user_id": current_user.id},
            level="warning",
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )
    
    # Check if new password is different from current
    if verify_password(request.new_password, current_user.hashed_password):
        log_security_event(
            event_type="password_change_failed",
            details={"reason": "same_password", "user_id": current_user.id},
            level="warning",
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )
    
    # Hash new password and update user
    new_hashed_password = get_password_hash(request.new_password)
    current_user.hashed_password = new_hashed_password
    current_user.password_changed_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(current_user)
    
    # Log successful password change
    log_security_event(
        event_type="password_changed",
        details={"user_id": current_user.id, "email": current_user.email},
        level="info",
        user_id=current_user.id
    )
    
    return ChangePasswordResponse(
        success=True,
        message="Password changed successfully"
    )


@router.put("/change-username", response_model=ChangeUsernameResponse)
async def change_username(
    request: ChangeUsernameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ChangeUsernameResponse:
    """
    Change user's account name/username.
    
    Updates the display name for the user account.
    """
    
    # Validate name length and content
    new_name = request.new_name.strip()
    if len(new_name) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name cannot be empty"
        )
    
    if len(new_name) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name is too long (maximum 100 characters)"
        )
    
    # Check if name is different from current
    if current_user.name == new_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New name must be different from current name"
        )
    
    # Update user name
    old_name = current_user.name
    current_user.name = new_name
    
    await db.commit()
    await db.refresh(current_user)
    
    # Log name change
    log_security_event(
        event_type="username_changed",
        details={
            "user_id": current_user.id, 
            "email": current_user.email,
            "old_name": old_name,
            "new_name": new_name
        },
        level="info",
        user_id=current_user.id
    )
    
    return ChangeUsernameResponse(
        success=True,
        message="Account name changed successfully",
        name=new_name
    )


# JWT Cookie Migration Endpoints

@router.post("/migrate-to-cookies")
async def migrate_to_cookies(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Migration endpoint for existing localStorage users.
    Converts header-based auth to HTTP-only cookies.
    """
    try:
        # User is authenticated via Authorization header, now set cookies
        await enhanced_auth_service.set_auth_cookies(
            response, current_user.id, remember_me=False
        )
        
        log_security_event(
            event_type="auth_migration_to_cookies",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "client_ip": get_client_ip(request)
            },
            level="info",
            user_id=current_user.id
        )
        
        return {
            "success": True,
            "message": "Successfully migrated to cookie-based authentication",
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "name": current_user.name
            }
        }
    except Exception as e:
        logger.error(f"Cookie migration failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to migrate to cookie authentication"
        )


@router.get("/cookie-support")
async def check_cookie_support() -> Dict[str, Any]:
    """
    Check if backend supports cookie-based authentication.
    Used by frontend to determine migration capability.
    """
    return {
        "supported": True,
        "csrf_enabled": settings.CSRF_ENABLED,
        "csrf_header": settings.CSRF_HEADER_NAME,
        "secure_cookies": settings.COOKIE_SECURE,
        "same_site": settings.COOKIE_SAMESITE
    }


@router.post("/validate-csrf")
async def validate_csrf_token(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Validate CSRF token for testing purposes.
    Helps debug CSRF protection issues.
    """
    if not settings.CSRF_ENABLED:
        return {
            "csrf_enabled": False,
            "message": "CSRF protection is disabled"
        }
    
    csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)
    csrf_cookie = request.cookies.get("csrf_token")
    
    return {
        "csrf_enabled": True,
        "csrf_header_present": bool(csrf_header),
        "csrf_cookie_present": bool(csrf_cookie),
        "tokens_match": csrf_header == csrf_cookie if csrf_header and csrf_cookie else False,
        "csrf_header_name": settings.CSRF_HEADER_NAME
    }



