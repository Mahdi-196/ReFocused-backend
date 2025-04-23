from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from app.core.security import verify_password, create_access_token, create_refresh_token, get_password_hash
from app.db.session import get_db
from app.models.user import User
from app.models.token import TokenBlacklist
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserResponse
from app.core.security_config import security_config
from app.utils.rate_limiter import rate_limit
# from app.utils.security_logger import log_security_event # Commented out unused import
from app.core.config import settings
from datetime import timedelta

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.post("/login", response_model=dict)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # Get user from database
    user = await db.get(User, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create tokens
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> Any:
    """Refresh access token."""
    try:
        payload = jwt.decode(
            token, security_config.SECRET_KEY, algorithms=[security_config.ALGORITHM]
        )
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Check if token is blacklisted
        if await TokenBlacklist.is_blacklisted(db, token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated"
            )
        
        # Generate new access token
        access_token = create_access_token(subject=user_id)
        return {"access_token": access_token, "token_type": "bearer"}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

@router.post("/register", response_model=dict)
async def register(
    username: str,
    email: str,
    password: str,
    full_name: str,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Register a new user
    """
    # Check if user exists
    existing_user = await db.get(User, username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Create new user
    new_user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name
    )
    db.add(new_user)
    await db.commit()
    
    return {"message": "User created successfully"}

@router.post("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> Any:
    """Logout user by blacklisting the token."""
    try:
        payload = jwt.decode(
            token, security_config.SECRET_KEY, algorithms=[security_config.ALGORITHM]
        )
        expires_at = datetime.fromtimestamp(payload["exp"])
        await TokenBlacklist.add_token(db, token, expires_at)
        return {"message": "Successfully logged out"}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        ) 