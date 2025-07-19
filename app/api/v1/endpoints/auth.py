from datetime import datetime, timedelta
from typing import Any, Optional, Dict

from fastapi import APIRouter, Request, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    log_security_event,
)
from app.core.auth import get_current_user, oauth2_scheme  # Import centralized oauth2_scheme
from app.db.database import get_db
from app.db.models import User
from app.db.models import TokenBlacklist
from app.schemas.token import TokenResponse
from app.schemas.google_auth import GoogleAuthRequest, GoogleAuthResponse, UserResponse
from app.services.google_oauth import GoogleOAuthService, GoogleTokenValidationError
# from app.services.journal_service import JournalService  # Temporarily disabled
from app.core.config import settings
from app.core.enhanced_auth import enhanced_auth_service
import logging

logger = logging.getLogger("auth_endpoints")

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None


class RegisterSchema(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class UserProfile(BaseModel):
    """User profile response."""
    id: int
    email: str
    name: str
    profile_picture: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    profile_picture: Optional[str] = None


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
    
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        data = await request.json()
        creds = EnhancedLoginRequest(**data)
        
        if settings.AUTH_REQUIRE_GRANT_TYPE and creds.grant_type != settings.AUTH_DEFAULT_GRANT_TYPE:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid grant_type, must be '{settings.AUTH_DEFAULT_GRANT_TYPE}'",
            )
        
        user = await authenticate_user(creds.email, creds.password, db)
        
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
        user = await authenticate_user(email, form["password"], db)
        
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
                payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                expires_at = datetime.fromtimestamp(payload["exp"])
                await TokenBlacklist.add_token(db, access_token, expires_at)
                user_id = payload.get("sub")
            except JWTError:
                pass  # Token already invalid
        
        # Blacklist refresh token if present
        if refresh_token:
            try:
                payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
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
        user_id = int(payload.get("sub"))
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        return EnhancedTokenResponse(
            access_token="set_in_cookie",  # Token is in cookie
            refresh_token="set_in_cookie",  # Refresh token is in cookie
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


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterSchema, db: AsyncSession = Depends(get_db)) -> Any:
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
    
    # Create access token for immediate login
    access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id}, 
        expires_delta=access_expires
    )
    refresh_token = create_refresh_token(
        data={"sub": user.email, "user_id": user.id}
    )
    
    return {
        "message": "User created successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
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
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
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
    if profile_data.profile_picture is not None:
        current_user.profile_picture = profile_data.profile_picture
    
    await db.commit()
    await db.refresh(current_user)
    
    # Log profile update
    log_security_event(
        event_type="profile_update",
        details={"updated_fields": [k for k, v in profile_data.dict().items() if v is not None]},
        level="info",
        user_id=current_user.id
    )
    
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture=current_user.profile_picture,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
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



