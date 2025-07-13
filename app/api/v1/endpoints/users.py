from typing import Any, Optional
from datetime import datetime

# FastAPI imports
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer

# Database imports
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

# Pydantic imports
from pydantic import BaseModel

# App imports
from app.core.config import settings
from app.core.security import log_security_event
from app.core.auth import get_current_user, jwt_required, oauth2_scheme
from app.db.database import get_db
from app.db.models import User, Goal2Week, GoalLongTerm, Habit, MoodEntry
from app.schemas.user import UserResponse, UserProfile, UserUpdate
from datetime import date

router = APIRouter()


class ProfileUpdate(BaseModel):
    """Schema for profile update requests."""
    name: Optional[str] = None
    profile_picture: Optional[str] = None


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
    
    # Count goals from both tables
    # Count 2-week goals (excluding expired)
    from datetime import timezone
    current_time = datetime.now(timezone.utc)
    
    goals_2week_total_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            Goal2Week.user_id == current_user.id,
            Goal2Week.expires_at > current_time
        )
    )
    goals_2week_total = goals_2week_total_result.scalar() or 0
    
    goals_2week_completed_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            Goal2Week.user_id == current_user.id,
            Goal2Week.is_completed == True,
            Goal2Week.expires_at > current_time
        )
    )
    goals_2week_completed = goals_2week_completed_result.scalar() or 0
    
    # Count long-term goals
    goals_longterm_total_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(GoalLongTerm.user_id == current_user.id)
    )
    goals_longterm_total = goals_longterm_total_result.scalar() or 0
    
    goals_longterm_completed_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            GoalLongTerm.user_id == current_user.id,
            GoalLongTerm.is_completed == True
        )
    )
    goals_longterm_completed = goals_longterm_completed_result.scalar() or 0
    
    # Combine totals
    goals_total = goals_2week_total + goals_longterm_total
    goals_completed = goals_2week_completed + goals_longterm_completed
    
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


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Delete the current user's account and all associated data permanently.
    
    This endpoint:
    - Deletes the user account and all related data (goals, habits, mood entries, etc.)
    - Uses CASCADE relationships to ensure complete data removal
    - Logs the deletion event for security audit
    - Cannot be undone - all data will be permanently lost
    
    Requires authentication via JWT token.
    """
    
    try:
        # Get user ID for logging (before deletion)
        user_id = current_user.id
        user_email = current_user.email
        
        # Log the account deletion attempt for security audit
        log_security_event(
            event_type="account_deletion_initiated",
            details={
                "user_id": user_id,
                "email": user_email,
                "deletion_timestamp": datetime.utcnow().isoformat()
            },
            level="warning",
            user_id=user_id
        )
        
        # Delete the user - CASCADE relationships will handle all related data
        await db.delete(current_user)
        await db.commit()
        
        # Log successful deletion (using user_id since user no longer exists)
        log_security_event(
            event_type="account_deletion_completed",
            details={
                "user_id": user_id,
                "email": user_email,
                "deletion_timestamp": datetime.utcnow().isoformat(),
                "status": "success"
            },
            level="info"
        )
        
        return {
            "message": "Account and all associated data have been permanently deleted",
            "status": "success",
            "deleted_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        # Rollback any partial changes
        await db.rollback()
        
        # Log deletion failure for security audit
        log_security_event(
            event_type="account_deletion_failed",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "error": str(e),
                "deletion_timestamp": datetime.utcnow().isoformat()
            },
            level="error",
            user_id=current_user.id
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account. Please try again or contact support."
        ) 