from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
import re

from pydantic import BaseModel, EmailStr, validator

from app.db.database import get_db
from app.db.models import User, TokenBlacklist
from app.core.auth import (
    TokenManager,
    AuthenticationManager,
    get_current_user,
    get_current_active_user
)
from app.core.config import settings
from app.utils.security import get_client_ip
from app.core.security import log_security_event, alert_authentication_failure

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    
    @validator('password')
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain an uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain a lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain a number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain a special character')
        return v

class Token(BaseModel):
    access_token: str
    token_type: str

class UserProfile(BaseModel):
    id: int
    email: str
    name: Optional[str]
    is_active: bool
    created_at: str

@router.post("/register", response_model=Token)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db), request: Request = None):
    """Register a new user and return an access token."""
    client_ip = get_client_ip(request) if request else "unknown"
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        # Log failed registration attempt due to existing email
        log_security_event(
            event_type="registration_duplicate",
            details={"email": user_data.email, "ip_address": client_ip},
            level="warning"
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash the password
    hashed_password = AuthenticationManager.get_password_hash(user_data.password)
    
    # Create new user
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        name=user_data.name,
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Log successful registration
    log_security_event(
        event_type="registration_success",
        details={"email": user_data.email, "ip_address": client_ip},
        level="info",
        user_id=new_user.id
    )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = TokenManager.create_access_token(
        data={"sub": new_user.email, "user_id": new_user.id}, 
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    request: Request = None
):
    """Authenticate user and return an access token."""
    client_ip = get_client_ip(request) if request else "unknown"
    
    # Find user by email
    user = db.query(User).filter(User.email == form_data.username).first()
    
    # Check if user exists and password is correct
    if not user or not AuthenticationManager.verify_password(form_data.password, user.hashed_password):
        # Log failed login attempt
        alert_authentication_failure(
            username=form_data.username,
            ip_address=client_ip,
            reason="Invalid credentials"
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        # Log inactive user login attempt
        alert_authentication_failure(
            username=form_data.username,
            ip_address=client_ip,
            reason="Inactive account"
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Log successful login
    log_security_event(
        event_type="login_success",
        details={"email": user.email, "ip_address": client_ip},
        level="info",
        user_id=user.id
    )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = TokenManager.create_access_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """Logout user by blacklisting the current token."""
    # Get the token from the request
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )
    
    token = auth_header.split(" ")[1]
    
    # Decode token to get expiration
    payload = TokenManager.verify_token(token, db)
    expires_at = payload.get("exp")
    
    # Add token to blacklist
    TokenBlacklist.add_token(db, token, expires_at)
    
    # Log logout
    client_ip = get_client_ip(request) if request else "unknown"
    log_security_event(
        event_type="logout",
        details={"email": current_user.email, "ip_address": client_ip},
        level="info",
        user_id=current_user.id
    )
    
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile information."""
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    )

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    profile_picture: Optional[str] = None

@router.put("/profile", response_model=UserProfile)
async def update_user_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """Update current user profile information."""
    client_ip = get_client_ip(request) if request else "unknown"
    
    # Update user fields
    if profile_data.name is not None:
        current_user.name = profile_data.name
    if profile_data.profile_picture is not None:
        current_user.profile_picture = profile_data.profile_picture
    
    db.commit()
    db.refresh(current_user)
    
    # Log profile update
    log_security_event(
        event_type="profile_update",
        details={"updated_fields": [k for k, v in profile_data.dict().items() if v is not None], "ip_address": client_ip},
        level="info",
        user_id=current_user.id
    )
    
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    ) 