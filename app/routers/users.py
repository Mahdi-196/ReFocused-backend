from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import List, Dict, Any
from datetime import date, timedelta

from app.db.database import get_db
from app.db.models import User, Goal2Week, GoalLongTerm, Habit, MoodEntry, StudySet, Mantra, JournalCollection
from app.core.auth import get_current_active_user

from pydantic import BaseModel, validator

router = APIRouter(prefix="/user", tags=["User"])

class UserResponse(BaseModel):
    id: int
    email: str  # Changed from EmailStr to avoid DNS lookups in VPC
    name: str = None
    profile_picture: str = None

    @validator('email')
    def validate_email(cls, v):
        import re
        if v and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower().strip() if v else v

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



@router.get("/stats", response_model=UserStats)
async def get_user_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user-specific statistics."""
    
    # Count goals from both tables
    from datetime import timezone, datetime
    current_time = datetime.now(timezone.utc)
    
    # Count 2-week goals (excluding expired)
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