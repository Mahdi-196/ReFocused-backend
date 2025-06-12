from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
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
from app.core.auth import get_current_user  # Import from core auth module
from app.db.session import get_db
from app.db.models import User
from app.db.models import TokenBlacklist
from app.schemas.token import TokenResponse
from app.schemas.google_auth import GoogleAuthRequest, GoogleAuthResponse, UserResponse
from app.services.google_oauth import GoogleOAuthService
from app.core.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=settings.AUTH_TOKEN_URL)


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
    id: int
    email: str
    name: Optional[str]
    profile_picture: Optional[str]
    is_active: bool
    created_at: Optional[str]


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    profile_picture: Optional[str] = None


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, db: AsyncSession = Depends(get_db)) -> Any:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        creds = LoginRequest(**data)
        if settings.AUTH_REQUIRE_GRANT_TYPE and creds.grant_type != settings.AUTH_DEFAULT_GRANT_TYPE:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid grant_type, must be '{settings.AUTH_DEFAULT_GRANT_TYPE}'",
            )
        user = await authenticate_user(creds.email, creds.password, db)
        
        # Log successful login
        log_security_event(
            event_type="login_success",
            details={"email": user.email, "user_id": user.id},
            level="info"
        )
        
        access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": user.id}, 
            expires_delta=access_expires
        )
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": user.id}
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            scope=creds.scope or "",
        )

    elif "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        grant = form.get("grant_type", settings.AUTH_DEFAULT_GRANT_TYPE)
        if settings.AUTH_REQUIRE_GRANT_TYPE and grant != settings.AUTH_DEFAULT_GRANT_TYPE:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid grant_type, must be '{settings.AUTH_DEFAULT_GRANT_TYPE}'",
            )
        
        # Support both 'username' and 'email' fields for OAuth2 compatibility
        email = form.get("username") or form.get("email")
        if not email:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Email is required"
            )
            
        user = await authenticate_user(email, form["password"], db)
        
        # Log successful login
        log_security_event(
            event_type="login_success",
            details={"email": user.email, "user_id": user.id},
            level="info"
        )
        
        access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": user.id}, 
            expires_delta=access_expires
        )
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": user.id}
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            scope=form.get("scope") or "",
        )

    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported Media Type",
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> Any:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        sub = payload.get("sub")
        user_id = payload.get("user_id")
        
        if not sub or await TokenBlacklist.is_blacklisted(db, token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or blacklisted token")
        
        # Create new access and refresh tokens
        new_access = create_access_token(data={"sub": sub, "user_id": user_id})
        new_refresh = create_refresh_token(data={"sub": sub, "user_id": user_id})
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        
        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=expires_in,
            scope=""
        )
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterSchema, db: AsyncSession = Depends(get_db)) -> Any:
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        name=data.name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
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


@router.post("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> Any:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        expires_at = datetime.fromtimestamp(payload["exp"])
        await TokenBlacklist.add_token(db, token, expires_at)
        
        # Log successful logout
        user_id = payload.get("user_id")
        if user_id:
            log_security_event(
                event_type="logout_success",
                details={"user_id": user_id},
                level="info"
            )
        
        return {"message": "Successfully logged out"}
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.post("/google", response_model=GoogleAuthResponse)
async def google_auth(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authenticate user with Google OAuth ID token.
    
    This endpoint:
    1. Verifies the Google ID token
    2. Creates a new user if they don't exist
    3. Returns a JWT access token for API access
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Google OAuth request received with token length: {len(request.token)}")
        
        google_service = GoogleOAuthService()
        
        # Verify Google token and extract user info
        logger.info("Attempting to verify Google token...")
        user_info = await google_service.verify_token(request.token)
        
        if not user_info:
            logger.warning("Google token verification failed - invalid token")
            log_security_event(
                event_type="google_auth_failed",
                details={"reason": "invalid_token"},
                level="warning"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token"
            )
        
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
            
            logger.info(f"New user created successfully: {user.email} (ID: {user.id})")
            
            log_security_event(
                event_type="user_created",
                details={"email": user.email, "provider": "google"},
                level="info",
                user_id=user.id
            )
        
        logger.info("Generating JWT access token...")
        
        # Generate JWT access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": user.id},
            expires_delta=access_token_expires
        )
        
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
            access_token=access_token,
            user=user_response,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Google OAuth: {str(e)}", exc_info=True)
        await db.rollback()
        log_security_event(
            event_type="google_auth_error",
            details={"error": str(e), "error_type": type(e).__name__},
            level="error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
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
