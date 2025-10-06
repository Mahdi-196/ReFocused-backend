"""
Admin endpoints for superuser management and system administration.
"""

from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, validator

from app.db.database import get_db
from app.db.models import User
from app.core.security import get_password_hash, log_security_event
from app.core.auth import AuthenticationManager


router = APIRouter()


# Schemas
class SuperuserCreateRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

    @validator('email')
    def validate_email(cls, v):
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower().strip()


class SuperuserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]
    is_superuser: bool
    is_active: bool
    auth_provider: str
    created_at: str
    last_login: Optional[str]


class SuperuserListResponse(BaseModel):
    superusers: List[SuperuserResponse]
    total_count: int


# Dependencies
async def get_superuser_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to ensure only superusers can access admin endpoints.
    """
    from app.core.auth_middleware import get_current_user
    
    # Get current user (this handles token validation)
    current_user = await get_current_user(request, db)
    
    if not current_user.is_superuser:
        # Log unauthorized access attempt
        log_security_event(
            event_type="admin_access_denied",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "endpoint": str(request.url),
                "method": request.method
            },
            level="warning"
        )
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required. This endpoint is only available to superusers."
        )
    
    return current_user


# Endpoints
@router.post("/superuser", response_model=SuperuserResponse, status_code=status.HTTP_201_CREATED)
async def create_superuser(
    request: SuperuserCreateRequest,
    current_superuser: User = Depends(get_superuser_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Create a new superuser account.
    
    **Requires superuser privileges.**
    
    This endpoint allows existing superusers to create additional superuser accounts.
    The password must meet all security requirements.
    """
    
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == request.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{request.email}' already exists"
        )
    
    # Validate password strength
    if not AuthenticationManager.validate_password_strength(request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet security requirements"
        )
    
    # Create new superuser
    new_superuser = User(
        email=request.email,
        hashed_password=get_password_hash(request.password),
        name=request.name or request.email.split("@")[0].title(),
        is_active=True,
        is_superuser=True,
        auth_provider="local"
    )
    
    db.add(new_superuser)
    await db.commit()
    await db.refresh(new_superuser)
    
    # Log security event
    log_security_event(
        event_type="superuser_created_via_api",
        details={
            "created_by_user_id": current_superuser.id,
            "created_by_email": current_superuser.email,
            "new_superuser_id": new_superuser.id,
            "new_superuser_email": new_superuser.email
        },
        level="info"
    )
    
    return SuperuserResponse(
        id=new_superuser.id,
        email=new_superuser.email,
        name=new_superuser.name,
        is_superuser=new_superuser.is_superuser,
        is_active=new_superuser.is_active,
        auth_provider=new_superuser.auth_provider,
        created_at=new_superuser.created_at.isoformat() if new_superuser.created_at else None,
        last_login=new_superuser.last_login.isoformat() if new_superuser.last_login else None
    )


@router.get("/superusers", response_model=SuperuserListResponse)
async def list_superusers(
    current_superuser: User = Depends(get_superuser_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    List all superuser accounts.
    
    **Requires superuser privileges.**
    
    Returns a list of all users with superuser privileges.
    """
    
    # Get all superusers
    result = await db.execute(
        select(User).where(User.is_superuser == True).order_by(User.created_at.desc())
    )
    superusers = result.scalars().all()
    
    # Get total count
    count_result = await db.execute(
        select(func.count(User.id)).where(User.is_superuser == True)
    )
    total_count = count_result.scalar()
    
    superuser_responses = [
        SuperuserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            is_superuser=user.is_superuser,
            is_active=user.is_active,
            auth_provider=user.auth_provider,
            created_at=user.created_at.isoformat() if user.created_at else None,
            last_login=user.last_login.isoformat() if user.last_login else None
        )
        for user in superusers
    ]
    
    return SuperuserListResponse(
        superusers=superuser_responses,
        total_count=total_count
    )


@router.patch("/user/{user_id}/promote", response_model=SuperuserResponse)
async def promote_user_to_superuser(
    user_id: int,
    current_superuser: User = Depends(get_superuser_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Promote an existing user to superuser.
    
    **Requires superuser privileges.**
    
    This endpoint allows existing superusers to promote regular users to superuser status.
    """
    
    # Get the user to promote
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a superuser"
        )
    
    # Promote user
    user.is_superuser = True
    await db.commit()
    await db.refresh(user)
    
    # Log security event
    log_security_event(
        event_type="user_promoted_to_superuser",
        details={
            "promoted_by_user_id": current_superuser.id,
            "promoted_by_email": current_superuser.email,
            "promoted_user_id": user.id,
            "promoted_user_email": user.email
        },
        level="info"
    )
    
    return SuperuserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_superuser=user.is_superuser,
        is_active=user.is_active,
        auth_provider=user.auth_provider,
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login=user.last_login.isoformat() if user.last_login else None
    )


@router.patch("/user/{user_id}/demote", response_model=SuperuserResponse)
async def demote_superuser(
    user_id: int,
    current_superuser: User = Depends(get_superuser_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Remove superuser privileges from a user.
    
    **Requires superuser privileges.**
    
    This endpoint allows existing superusers to remove superuser privileges from other users.
    Note: You cannot demote yourself to prevent lockout scenarios.
    """
    
    # Prevent self-demotion
    if user_id == current_superuser.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote yourself. Use another superuser account to demote this account."
        )
    
    # Get the user to demote
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a superuser"
        )
    
    # Demote user
    user.is_superuser = False
    await db.commit()
    await db.refresh(user)
    
    # Log security event
    log_security_event(
        event_type="superuser_demoted",
        details={
            "demoted_by_user_id": current_superuser.id,
            "demoted_by_email": current_superuser.email,
            "demoted_user_id": user.id,
            "demoted_user_email": user.email
        },
        level="warning"  # This is a significant security action
    )
    
    return SuperuserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_superuser=user.is_superuser,
        is_active=user.is_active,
        auth_provider=user.auth_provider,
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login=user.last_login.isoformat() if user.last_login else None
    )


@router.get("/system/info")
async def get_system_info(
    current_superuser: User = Depends(get_superuser_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get system information and statistics.
    
    **Requires superuser privileges.**
    
    Returns various system statistics and information for administrative purposes.
    """
    
    # Get user statistics
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar()
    
    active_users_result = await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )
    active_users = active_users_result.scalar()
    
    superusers_result = await db.execute(
        select(func.count(User.id)).where(User.is_superuser == True)
    )
    total_superusers = superusers_result.scalar()
    
    google_users_result = await db.execute(
        select(func.count(User.id)).where(User.auth_provider == "google")
    )
    google_users = google_users_result.scalar()
    
    return {
        "system": {
            "name": "ReFocused Backend",
            "version": "1.0.0",
            "environment": "production"
        },
        "users": {
            "total": total_users,
            "active": active_users,
            "inactive": total_users - active_users,
            "superusers": total_superusers,
            "google_oauth": google_users,
            "local_auth": total_users - google_users
        },
        "current_superuser": {
            "id": current_superuser.id,
            "email": current_superuser.email,
            "name": current_superuser.name
        }
    } 