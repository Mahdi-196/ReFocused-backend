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
)
from app.db.session import get_db
from app.models.user import User
from app.models.token import TokenBlacklist
from app.schemas.token import TokenResponse
from app.core.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=settings.AUTH_TOKEN_URL)


class LoginRequest(BaseModel):
    username: str
    password: str
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None


class RegisterSchema(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None


async def authenticate_user(username: str, password: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
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
        user = await authenticate_user(creds.username, creds.password, db)
        access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(data={"sub": user.username}, expires_delta=access_expires)
        refresh_token = create_refresh_token(data={"sub": user.username})
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
        user = await authenticate_user(form["username"], form["password"], db)
        access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(data={"sub": user.username}, expires_delta=access_expires)
        refresh_token = create_refresh_token(data={"sub": user.username})
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
        if not sub or await TokenBlacklist.is_blacklisted(db, token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or blacklisted token")
        
        # Create new access and refresh tokens
        new_access = create_access_token(data={"sub": sub})
        new_refresh = create_refresh_token(data={"sub": sub})
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
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return {"message": "User created successfully"}


@router.post("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> Any:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        expires_at = datetime.fromtimestamp(payload["exp"])
        await TokenBlacklist.add_token(db, token, expires_at)
        return {"message": "Successfully logged out"}
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
