from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import List, Dict, Any
from datetime import date, timedelta

from app.db.database import get_db
from app.db.models import User, Goal, Habit, MoodEntry, StudySet, Mantra, JournalCollection
from app.core.auth import get_current_active_user

from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/user", tags=["User"])

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str = None
    profile_picture: str = None
    
    class Config:
        from_attributes = True

class UserStats(BaseModel):
    goals_total: int
    goals_completed: int
    habits_total: int
    mood_entries_count: int
    study_sets_count: int
    mantras_count: int
    journal_collections_count: int
    account_age_days: int

@router.get("/me", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get the current user's profile."""
    return current_user

@router.get("/stats", response_model=UserStats)
async def get_user_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user-specific statistics."""
    
    # Count goals
    goals_total_result = await db.execute(select(func.count(Goal.id)).where(Goal.user_id == current_user.id))
    goals_total = goals_total_result.scalar() or 0
    
    goals_completed_result = await db.execute(
        select(func.count(Goal.id)).where(
            Goal.user_id == current_user.id,
            Goal.is_completed == True
        )
    )
    goals_completed = goals_completed_result.scalar() or 0
    
    # Count habits
    habits_total_result = await db.execute(select(func.count(Habit.id)).where(Habit.user_id == current_user.id))
    habits_total = habits_total_result.scalar() or 0
    
    # Count mood entries
    mood_entries_result = await db.execute(select(func.count(MoodEntry.id)).where(MoodEntry.user_id == current_user.id))
    mood_entries_count = mood_entries_result.scalar() or 0
    
    # Count study sets
    study_sets_result = await db.execute(select(func.count(StudySet.id)).where(StudySet.user_id == current_user.id))
    study_sets_count = study_sets_result.scalar() or 0
    
    # Count mantras
    mantras_result = await db.execute(select(func.count(Mantra.id)).where(Mantra.user_id == current_user.id))
    mantras_count = mantras_result.scalar() or 0
    
    # Count journal collections
    journal_collections_result = await db.execute(select(func.count(JournalCollection.id)).where(JournalCollection.user_id == current_user.id))
    journal_collections_count = journal_collections_result.scalar() or 0
    
    # Calculate account age
    account_age_days = 0
    if current_user.created_at:
        account_age_days = (date.today() - current_user.created_at.date()).days
    
    return UserStats(
        goals_total=goals_total,
        goals_completed=goals_completed,
        habits_total=habits_total,
        mood_entries_count=mood_entries_count,
        study_sets_count=study_sets_count,
        mantras_count=mantras_count,
        journal_collections_count=journal_collections_count,
        account_age_days=account_age_days
    ) 