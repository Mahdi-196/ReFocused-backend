from typing import Any, Optional

# FastAPI imports
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Database imports
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

# Pydantic imports
from pydantic import BaseModel

# App imports
from app.core.config import settings
from app.core.security import log_security_event
from app.core.auth import get_current_user, jwt_required
from app.db.session import get_db
from app.db.models import User, Goal, Habit, MoodEntry
from app.schemas.user import UserResponse
from datetime import date

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=settings.AUTH_TOKEN_URL)


class ProfileUpdate(BaseModel):
    """Schema for profile update requests."""
    name: Optional[str] = None
    profile_picture: Optional[str] = None


class UserProfile(BaseModel):
    """Schema for user profile response."""
    id: int
    email: str
    name: Optional[str]
    profile_picture: Optional[str]
    is_active: bool
    created_at: Optional[str]


class UserStats(BaseModel):
    """Schema for user statistics response."""
    goals_total: int
    goals_completed: int
    habits_total: int
    mood_entries_count: int
    account_age_days: int


@router.get("/me", response_model=UserProfile)
async def read_own_profile(
    current_user: User = Depends(get_current_user)
) -> UserProfile:
    """
    Get the profile of the currently authenticated user.
    """
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture=current_user.profile_picture,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    )


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Alternative endpoint for getting user profile.
    """
    return current_user


@router.patch("/profile", response_model=UserProfile)
async def update_user_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """
    Update current user profile information.
    Supports updating name and profile_picture fields.
    Uses standard JWT authentication (consistent with other endpoints).
    """
    
    # Track which fields are being updated
    updated_fields = []
    
    # Update user fields
    if profile_data.name is not None:
        current_user.name = profile_data.name
        updated_fields.append("name")
        
    if profile_data.profile_picture is not None:
        current_user.profile_picture = profile_data.profile_picture
        updated_fields.append("profile_picture")
    
    # Save changes to database
    await db.commit()
    await db.refresh(current_user)
    
    # Log profile update for security tracking
    log_security_event(
        event_type="profile_update",
        details={"updated_fields": updated_fields},
        level="info",
        user_id=current_user.id
    )
    
    # Return updated profile
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture=current_user.profile_picture,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    )


@router.put("/profile", response_model=UserProfile)
async def update_user_profile_put(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """
    Update current user profile information (PUT method).
    Supports updating name and profile_picture fields.
    Uses standard JWT authentication (consistent with other endpoints).
    """
    return await update_user_profile(profile_data, current_user, db)


@router.get("/stats", response_model=UserStats)
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserStats:
    """
    Get user-specific statistics.
    Provides comprehensive analytics about user activity.
    """
    
    # Count goals
    goals_total_result = await db.execute(
        select(func.count(Goal.id)).where(Goal.user_id == current_user.id)
    )
    goals_total = goals_total_result.scalar() or 0
    
    goals_completed_result = await db.execute(
        select(func.count(Goal.id)).where(
            Goal.user_id == current_user.id,
            Goal.is_completed == True
        )
    )
    goals_completed = goals_completed_result.scalar() or 0
    
    # Count habits
    habits_total_result = await db.execute(
        select(func.count(Habit.id)).where(Habit.user_id == current_user.id)
    )
    habits_total = habits_total_result.scalar() or 0
    
    # Count mood entries
    mood_entries_result = await db.execute(
        select(func.count(MoodEntry.id)).where(MoodEntry.user_id == current_user.id)
    )
    mood_entries_count = mood_entries_result.scalar() or 0
    
    # Calculate account age
    account_age_days = 0
    if current_user.created_at:
        account_age_days = (date.today() - current_user.created_at.date()).days
    
    return UserStats(
        goals_total=goals_total,
        goals_completed=goals_completed,
        habits_total=habits_total,
        mood_entries_count=mood_entries_count,
        account_age_days=account_age_days
    ) 