from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, timedelta
from sqlalchemy import select, and_, extract

from app.db.database import get_db
from app.core.auth import get_current_user
from app.db.models import Habit, HabitStreak, MoodEntry
from app.schemas.dashboard import DailyEntryResponse, DailyEntryCreate
from app.schemas.habit import HabitCompletionResponse
from app.schemas.mood import MoodResponse
from app.schemas.user import UserInDB
from app.crud.habit import HabitCRUD
from app.crud.mood import MoodCRUD

router = APIRouter()

@router.get("/daily-entries", response_model=List[DailyEntryResponse])
async def get_daily_entries(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM format)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """Get daily entries (mood + habit completions) for a month"""
    try:
        # Parse month parameter
        if month:
            year, month_num = map(int, month.split('-'))
            # Get first and last day of the month
            start_date = date(year, month_num, 1)
            if month_num == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month_num + 1, 1) - timedelta(days=1)
        else:
            # Default to current month
            today = date.today()
            start_date = date(today.year, today.month, 1)
            if today.month == 12:
                end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

        # Get mood entries for the month
        mood_entries = await MoodCRUD.get_mood_entries(db, current_user.id, month)
        mood_by_date = {entry.entry_date: entry for entry in mood_entries}

        # Get all habits for the user
        habits = await HabitCRUD.get_habits(db, current_user.id)
        habit_ids = [habit.id for habit in habits]

        # Get habit completions for the month
        habit_completions = {}
        if habit_ids:
            result = await db.execute(
                select(HabitStreak).where(
                    and_(
                        HabitStreak.habit_id.in_(habit_ids),
                        HabitStreak.date >= start_date,
                        HabitStreak.date <= end_date
                    )
                ).order_by(HabitStreak.date)
            )
            streaks = result.scalars().all()
            
            # Group by date
            for streak in streaks:
                if streak.date not in habit_completions:
                    habit_completions[streak.date] = []
                habit_completions[streak.date].append(streak)

        # Create daily entries
        daily_entries = []
        current_date = start_date
        
        while current_date <= end_date:
            # Get mood for this date
            mood_entry = mood_by_date.get(current_date)
            mood_response = None
            if mood_entry:
                mood_response = MoodResponse(
                    id=mood_entry.id,
                    happiness=mood_entry.happiness,
                    satisfaction=mood_entry.satisfaction,
                    stress=mood_entry.stress,
                    day_rating=mood_entry.day_rating,
                    note=mood_entry.note,
                    date=mood_entry.entry_date,
                    created_at=mood_entry.created_at
                )

            # Get habit completions for this date
            completions = habit_completions.get(current_date, [])
            completion_responses = [
                HabitCompletionResponse(
                    id=streak.id,
                    habit_id=streak.habit_id,
                    completed=True,
                    date=streak.date,
                    created_at=datetime.now()  # Placeholder
                )
                for streak in completions
            ]

            # Only include dates that have either mood or habit data
            if mood_response or completion_responses:
                daily_entries.append(DailyEntryResponse(
                    date=current_date,
                    mood=mood_response,
                    habit_completions=completion_responses
                ))

            current_date += timedelta(days=1)

        return daily_entries

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid month format. Use YYYY-MM"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get daily entries: {str(e)}"
        )

@router.post("/daily-entries", status_code=status.HTTP_201_CREATED)
async def create_daily_entry(
    entry: DailyEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """Create or update a daily entry with mood and habit completions"""
    try:
        # Create/update mood entry if mood data provided
        if any([entry.happiness, entry.satisfaction, entry.stress, entry.day_rating]):
            from app.schemas.mood import MoodCreate
            mood_data = MoodCreate(
                date=entry.date,
                happiness=entry.happiness or 3,
                satisfaction=entry.satisfaction or 3,
                stress=entry.stress or 3,
                day_rating=entry.day_rating or 5,
                note=entry.note
            )
            await MoodCRUD.upsert_mood_entry(db, mood_data, current_user.id)

        # Handle habit completions
        for completion in entry.habit_completions:
            habit_id = completion.get('habit_id')
            completed = completion.get('completed', False)
            
            if habit_id:
                if completed:
                    await HabitCRUD.mark_habit_complete(db, habit_id, current_user.id, entry.date)
                else:
                    await HabitCRUD.unmark_habit_complete(db, habit_id, current_user.id, entry.date)

        return {"message": "Daily entry created/updated successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create daily entry: {str(e)}"
        ) 