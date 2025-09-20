from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, timedelta
from sqlalchemy import select, and_, extract

from app.db.database import get_db
from app.core.auth import get_current_user
from app.db.models import Habit, HabitCompletion, MoodEntry
from app.schemas.dashboard import DailyEntryResponse, DailyEntryCreate
from app.schemas.habit import HabitCompletionResponse
from app.schemas.mood import MoodResponse
from app.db.models import User
from app.crud.habit import habit_crud
from app.crud.mood import MoodCRUD
from app.crud.journal import GratitudeCRUD  # Add gratitude CRUD import
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

def safe_get_mood_field(mood_entry: MoodEntry, field_name: str, default=None):
    """Safely get a field from mood entry, handling missing fields gracefully."""
    try:
        return getattr(mood_entry, field_name, default)
    except AttributeError:
        logger.warning(f"Field '{field_name}' not found on MoodEntry model - using default value {default}")
        return default

@router.get("/daily-entries", response_model=List[DailyEntryResponse])
async def get_daily_entries(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM format)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get daily entries (mood + habit completions) for a month"""
    return await _get_daily_entries_impl(month, db, current_user)

@router.get("/entries")
async def get_entries_alias(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM format)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dashboard entries in the format expected by frontend - object with date keys"""
    try:
        # Parse month parameter
        if month:
            try:
                year, month_num = map(int, month.split('-'))
                # Get first and last day of the month
                start_date = date(year, month_num, 1)
                if month_num == 12:
                    end_date = date(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = date(year, month_num + 1, 1) - timedelta(days=1)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid month format. Use YYYY-MM"
                )
        else:
            # Default to current month
            from app.core.config import settings
            today = settings.get_current_date()
            start_date = date(today.year, today.month, 1)
            if today.month == 12:
                end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

        # Get mood entries for the month with error handling
        try:
            mood_entries = await MoodCRUD.get_mood_entries(db, current_user.id, month=month)
            mood_by_date = {entry.entry_date: entry for entry in mood_entries}
        except Exception as e:
            logger.error(f"Error fetching mood entries for user {current_user.id}: {str(e)}")
            mood_by_date = {}

        # Get all habits for the user
        habits = await habit_crud.get_habits_with_reset_check(db, current_user)
        habit_ids = [habit.id for habit in habits]

        # Get habit completions for the month
        habit_completions = {}
        if habit_ids:
            try:
                result = await db.execute(
                    select(HabitCompletion).where(
                        and_(
                            HabitCompletion.habit_id.in_(habit_ids),
                            HabitCompletion.date >= start_date,
                            HabitCompletion.date <= end_date,
                            HabitCompletion.completed == True
                        )
                    ).order_by(HabitCompletion.date)
                )
                completions = result.scalars().all()
                
                # Group by date
                for completion in completions:
                    if completion.date not in habit_completions:
                        habit_completions[completion.date] = []
                    habit_completions[completion.date].append(completion)
            except Exception as e:
                logger.error(f"Error fetching habit completions for user {current_user.id}: {str(e)}")
                habit_completions = {}

        # Get gratitude entries for the month
        try:
            gratitude_entries, _ = await GratitudeCRUD.get_user_gratitude(
                db, current_user.id, 
                start_date=start_date, 
                end_date=end_date,
                limit=1000  # Get all gratitudes for the month
            )
            gratitude_by_date = {}
            for entry in gratitude_entries:
                if entry.date not in gratitude_by_date:
                    gratitude_by_date[entry.date] = []
                gratitude_by_date[entry.date].append(entry)
        except Exception as e:
            logger.error(f"Error fetching gratitude entries for user {current_user.id}: {str(e)}")
            gratitude_by_date = {}

        # Create entries object with date keys (as expected by frontend)
        entries = {}
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # Get mood for this date
            mood_entry = mood_by_date.get(current_date)
            
            # Get habit completions for this date
            completions = habit_completions.get(current_date, [])
            
            # Get gratitudes for this date
            gratitudes = gratitude_by_date.get(current_date, [])
            
            # Create entry structure expected by frontend with safe field access
            try:
                entry = {
                    "date": date_str,
                    "happiness": mood_entry.happiness if mood_entry else None,
                    "focus": mood_entry.focus if mood_entry else None,
                    "stress": mood_entry.stress if mood_entry else None,
                    # Handle missing day_rating field gracefully (removed in migration)
                    "dayRating": safe_get_mood_field(mood_entry, 'day_rating', None) if mood_entry else None,
                    # Handle missing note field gracefully (removed in migration)  
                    "notes": safe_get_mood_field(mood_entry, 'note', None) if mood_entry else None,
                    "habitCompletions": [
                        {"habitId": completion.habit_id, "completed": True}
                        for completion in completions
                    ] if completions else [],
                    "gratitudes": [  # Add gratitudes field
                        {
                            "id": gratitude.id,
                            "text": gratitude.text,
                            "date": gratitude.date.isoformat(),
                            "user_id": gratitude.user_id,
                            "created_at": gratitude.created_at.isoformat(),
                            "createdAt": gratitude.created_at.isoformat()
                        }
                        for gratitude in gratitudes
                    ],
                    "focusTime": 0,  # Placeholder - can be implemented later
                    "tasks": 0,      # Placeholder - can be implemented later
                    "sessions": 0    # Placeholder - can be implemented later
                }
            except Exception as e:
                logger.error(f"Error serializing mood data for date {date_str}, user {current_user.id}: {str(e)}")
                # Provide fallback entry structure
                entry = {
                    "date": date_str,
                    "happiness": None,
                    "focus": None,
                    "stress": None,
                    "dayRating": None,
                    "notes": None,
                    "habitCompletions": [
                        {"habitId": completion.habit_id, "completed": True}
                        for completion in completions
                    ] if completions else [],
                    "gratitudes": [  # Add gratitudes field even in fallback
                        {
                            "id": gratitude.id,
                            "text": gratitude.text,
                            "date": gratitude.date.isoformat(),
                            "user_id": gratitude.user_id,
                            "created_at": gratitude.created_at.isoformat(),
                            "createdAt": gratitude.created_at.isoformat()
                        }
                        for gratitude in gratitudes
                    ],
                    "focusTime": 0,
                    "tasks": 0,
                    "sessions": 0
                }
            
            # Always include the entry (frontend expects all dates in the month)
            entries[date_str] = entry
            current_date += timedelta(days=1)

        return entries

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get dashboard entries for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dashboard entries. Please try again later."
        )

async def _get_daily_entries_impl(
    month: Optional[str],
    db: AsyncSession,
    current_user: User
) -> List[DailyEntryResponse]:
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
            # Default to current month - use configurable date for testing
            from app.core.config import settings
            today = settings.get_current_date()
            start_date = date(today.year, today.month, 1)
            if today.month == 12:
                end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

        # Get mood entries for the month
        mood_entries = await MoodCRUD.get_mood_entries(db, current_user.id, start_date=start_date, end_date=end_date)
        mood_by_date = {entry.entry_date: entry for entry in mood_entries}

        # Get all habits for the user
        habits = await habit_crud.get_habits_with_reset_check(db, current_user)
        habit_ids = [habit.id for habit in habits]

        # Get habit completions for the month
        habit_completions = {}
        if habit_ids:
            result = await db.execute(
                select(HabitCompletion).where(
                    and_(
                        HabitCompletion.habit_id.in_(habit_ids),
                        HabitCompletion.date >= start_date,
                        HabitCompletion.date <= end_date,
                        HabitCompletion.completed == True
                    )
                ).order_by(HabitCompletion.date)
            )
            completions = result.scalars().all()
            
            # Group by date
            for completion in completions:
                if completion.date not in habit_completions:
                    habit_completions[completion.date] = []
                habit_completions[completion.date].append(completion)

        # Get gratitude entries for the month
        try:
            gratitude_entries, _ = await GratitudeCRUD.get_user_gratitude(
                db, current_user.id, 
                start_date=start_date, 
                end_date=end_date,
                limit=1000  # Get all gratitudes for the month
            )
            gratitude_by_date = {entry.date: entry for entry in gratitude_entries}
        except Exception as e:
            logger.error(f"Error fetching gratitude entries for user {current_user.id}: {str(e)}")
            gratitude_by_date = {}

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
                    user_id=mood_entry.user_id,
                    date=mood_entry.entry_date,
                    happiness=mood_entry.happiness,
                    focus=mood_entry.focus,
                    stress=mood_entry.stress,
                    day_rating=safe_get_mood_field(mood_entry, 'day_rating', None),  # Use safe field access
                    note=safe_get_mood_field(mood_entry, 'note', None),  # Use safe field access
                    created_at=mood_entry.created_at,  # Use database field name due to alias
                    updated_at=None  # MoodEntry doesn't have updated_at field
                )

            # Get habit completions for this date
            completions = habit_completions.get(current_date, [])
            completion_responses = [
                HabitCompletionResponse(
                    id=completion.id,
                    habit_id=completion.habit_id,
                    completed=True,
                    date=completion.date,
                    completed_at=completion.completed_at.isoformat() if completion.completed_at else None,
                    timezone=completion.timezone
                )
                for completion in completions
            ]

            # Get gratitudes for this date
            gratitude_entry = gratitude_by_date.get(current_date)
            gratitude_responses = []
            if gratitude_entry:
                from app.schemas.journal import Gratitude
                gratitude_responses = [Gratitude(
                    id=gratitude_entry.id,
                    user_id=gratitude_entry.user_id,
                    text=gratitude_entry.text,
                    date=gratitude_entry.date,
                    created_at=gratitude_entry.created_at
                )]

            # Only include dates that have either mood, habit, or gratitude data
            if mood_response or completion_responses or gratitude_responses:
                daily_entries.append(DailyEntryResponse(
                    date=current_date,
                    mood=mood_response,
                    habit_completions=completion_responses,
                    gratitudes=gratitude_responses  # Add gratitudes
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
    current_user: User = Depends(get_current_user)
):
    """Create or update a daily entry with mood and habit completions"""
    try:
        # Create/update mood entry if mood data provided
        # Note: day_rating field was removed from mood entries - only use happiness, focus, stress
        if any([entry.happiness, entry.focus, entry.stress]):
            try:
                from app.schemas.mood import MoodCreate
                
                # Create mood data without day_rating (field was removed from model)
                mood_data = MoodCreate(
                    date=entry.date,
                    happiness=entry.happiness or 3,
                    focus=entry.focus or 3,
                    stress=entry.stress or 3
                    # Note: day_rating and note fields removed from MoodEntry model
                )
                await MoodCRUD.upsert_mood_entry(db, mood_data, current_user.id)
                logger.info(f"Updated mood entry for user {current_user.id} on {entry.date}")
                
            except Exception as e:
                logger.error(f"Error creating/updating mood entry for user {current_user.id}: {str(e)}")
                # Don't fail the entire request if mood update fails
                pass

        # Handle habit completions with error handling
        if entry.habit_completions:
            try:
                for completion in entry.habit_completions:
                    habit_id = completion.get('habit_id')
                    completed = completion.get('completed', False)
                    
                    if habit_id:
                        await habit_crud.mark_habit_completion(
                            db, habit_id, entry.date, completed, current_user
                        )
                        
                logger.info(f"Updated {len(entry.habit_completions)} habit completions for user {current_user.id} on {entry.date}")
                
            except Exception as e:
                logger.error(f"Error updating habit completions for user {current_user.id}: {str(e)}")
                # Don't fail the entire request if habit updates fail
                pass

        return {
            "message": "Daily entry created/updated successfully",
            "date": entry.date.isoformat(),
            "mood_updated": any([entry.happiness, entry.focus, entry.stress]),
            "habits_updated": len(entry.habit_completions) if entry.habit_completions else 0
        }

    except Exception as e:
        logger.error(f"Failed to create daily entry for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create daily entry. Please try again later."
        ) 