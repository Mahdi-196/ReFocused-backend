from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
import logging

from app.db.database import get_db
from app.core.auth import get_current_user
from app.crud.calendar import calendar_crud
from app.schemas.calendar import (
    CalendarEntryCreate, CalendarEntryUpdate, CalendarEntryResponse,
    CalendarEntriesRangeResponse, CalendarError
)
from app.db.models import User

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
    responses={
        404: {"description": "Calendar entry not found"},
        403: {"description": "Access forbidden - read-only date"},
        400: {"description": "Invalid request"},
        422: {"description": "Validation error"}
    }
)

logger = logging.getLogger(__name__)

def get_user_timezone(x_user_timezone: Optional[str] = Header(None)) -> str:
    """Extract and validate user timezone from header"""
    if not x_user_timezone:
        return "UTC"
    
    # Basic validation
    if len(x_user_timezone) < 3 or '/' not in x_user_timezone:
        return "UTC"
    
    return x_user_timezone

@router.get("/entries", response_model=CalendarEntriesRangeResponse)
async def get_calendar_entries(
    start_date: str = Query(..., regex=r'^\d{4}-\d{2}-\d{2}$', description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., regex=r'^\d{4}-\d{2}-\d{2}$', description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Get calendar entries for a date range.
    
    This endpoint returns all calendar entries within the specified date range,
    including habit completions and mood entries. Entries are automatically
    locked for past dates based on the user's timezone.
    
    Headers:
    - X-User-Timezone: User's IANA timezone identifier (e.g., "America/New_York")
    """
    try:
        # Validate and parse dates
        try:
            start_date_obj = date.fromisoformat(start_date)
            end_date_obj = date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Validate date range
        if start_date_obj > end_date_obj:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_date must be before or equal to end_date"
            )
        
        # Limit date range to prevent excessive queries
        if (end_date_obj - start_date_obj).days > 365:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Date range cannot exceed 365 days"
            )
        
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Get calendar entries
        entries = await calendar_crud.get_calendar_entries(
            db, current_user, start_date_obj, end_date_obj
        )
        
        return CalendarEntriesRangeResponse(
            entries=entries,
            start_date=start_date_obj,
            end_date=end_date_obj,
            total_entries=len(entries)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting calendar entries: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve calendar entries"
        )

@router.get("/entries/{entry_date}", response_model=CalendarEntryResponse)
async def get_calendar_entry(
    entry_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Get a single calendar entry by date.
    
    Returns the complete calendar entry including habit completions and mood entry
    for the specified date. If no entry exists, returns 404.
    """
    try:
        # Validate and parse date
        try:
            date_obj = date.fromisoformat(entry_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Get calendar entry
        calendar_entry = await calendar_crud.get_calendar_entry(db, current_user, date_obj)
        
        if not calendar_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No calendar entry found for {entry_date}"
            )
        
        return calendar_entry
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting calendar entry for {entry_date}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve calendar entry"
        )

@router.post("/entries", response_model=CalendarEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_entry(
    entry_data: CalendarEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Create a new calendar entry.
    
    Creates a calendar entry with optional habit completions and mood entry.
    Cannot create entries for past dates (returns 403 Forbidden).
    
    Body should include:
    - date: The date for the entry (YYYY-MM-DD)
    - notes: Optional notes for the day
    - habit_completions: List of habit completion data
    - mood_entry: Optional mood data for the day
    """
    try:
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Create calendar entry
        calendar_entry = await calendar_crud.create_calendar_entry(db, current_user, entry_data)
        
        return calendar_entry
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating calendar entry: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create calendar entry"
        )

@router.put("/entries/{entry_date}", response_model=CalendarEntryResponse)
async def update_calendar_entry(
    entry_date: str,
    entry_data: CalendarEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Update an existing calendar entry.
    
    Updates the calendar entry for the specified date. Only allows updates
    for today and future dates. Past dates are read-only (returns 403 Forbidden).
    
    Partial updates are supported - only provide the fields you want to change.
    """
    try:
        # Validate and parse date
        try:
            date_obj = date.fromisoformat(entry_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Update calendar entry
        calendar_entry = await calendar_crud.update_calendar_entry(
            db, current_user, date_obj, entry_data
        )
        
        if not calendar_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No calendar entry found for {entry_date}"
            )
        
        return calendar_entry
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating calendar entry for {entry_date}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update calendar entry"
        )

@router.delete("/entries/{entry_date}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_entry(
    entry_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Delete a calendar entry.
    
    Deletes the calendar entry for the specified date, including all associated
    habit completions and mood entry. Only allows deletion for today and future
    dates. Past dates are read-only (returns 403 Forbidden).
    """
    try:
        # Validate and parse date
        try:
            date_obj = date.fromisoformat(entry_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Delete calendar entry
        deleted = await calendar_crud.delete_calendar_entry(db, current_user, date_obj)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No calendar entry found for {entry_date}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting calendar entry for {entry_date}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete calendar entry"
        )

@router.post("/entries/{entry_date}/sync", response_model=CalendarEntryResponse)
async def sync_calendar_entry(
    entry_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Sync calendar entry with existing habit completions and mood entries.
    
    This endpoint creates or updates a calendar entry by syncing it with
    existing habit completions and mood entries from the legacy systems.
    Useful for migrating or backfilling calendar data.
    """
    try:
        # Validate and parse date
        try:
            date_obj = date.fromisoformat(entry_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Sync calendar entry
        calendar_entry = await calendar_crud.sync_with_existing_data(
            db, current_user, date_obj
        )
        
        if not calendar_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existing data found to sync for {entry_date}"
            )
        
        return calendar_entry
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing calendar entry for {entry_date}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync calendar entry"
        )

@router.get("/summary")
async def get_calendar_summary(
    days: int = Query(30, ge=1, le=365, description="Number of days to include in summary"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Get calendar summary statistics.
    
    Returns summary statistics for the calendar including habit completion rates,
    mood averages, and other insights for the specified number of days.
    """
    try:
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Calculate date range
        from app.services.time_service import TimeService
        time_service = TimeService()
        end_date = time_service.get_user_current_date(current_user)
        start_date = end_date - timedelta(days=days)
        
        # Get calendar entries
        entries = await calendar_crud.get_calendar_entries(
            db, current_user, start_date, end_date
        )
        
        # Calculate summary statistics
        total_days = len(entries)
        days_with_habits = len([e for e in entries if e.habit_completions])
        days_with_mood = len([e for e in entries if e.mood_entry])
        
        # Habit completion rate
        total_habit_completions = sum(
            len([h for h in entry.habit_completions if h.completed]) 
            for entry in entries
        )
        total_habits = sum(len(entry.habit_completions) for entry in entries)
        habit_completion_rate = (total_habit_completions / total_habits * 100) if total_habits > 0 else 0
        
        # Mood averages
        mood_entries = [entry.mood_entry for entry in entries if entry.mood_entry]
        avg_happiness = sum(m.happiness for m in mood_entries) / len(mood_entries) if mood_entries else 0
        avg_focus = sum(m.focus for m in mood_entries) / len(mood_entries) if mood_entries else 0
        avg_stress = sum(m.stress for m in mood_entries) / len(mood_entries) if mood_entries else 0
        
        return {
            "period": {
                "start_date": start_date,
                "end_date": end_date,
                "total_days": days
            },
            "activity": {
                "entries_created": total_days,
                "days_with_habits": days_with_habits,
                "days_with_mood": days_with_mood
            },
            "habits": {
                "completion_rate": round(habit_completion_rate, 1),
                "total_completions": total_habit_completions,
                "total_opportunities": total_habits
            },
            "mood": {
                "average_happiness": round(avg_happiness, 1),
                "average_focus": round(avg_focus, 1),
                "average_stress": round(avg_stress, 1),
                "entries_count": len(mood_entries)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting calendar summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve calendar summary"
        ) 