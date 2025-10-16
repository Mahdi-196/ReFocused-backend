from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
import logging

from app.db.database import get_db
from app.core.auth import get_current_user
from app.crud.mood import MoodCRUD
from app.schemas.mood import MoodCreate, MoodUpdate, MoodResponse, TodayMoodCreate, TodayMoodUpdate
from app.db.models import User

router = APIRouter()
logger = logging.getLogger(__name__)

def get_user_timezone(x_user_timezone: Optional[str] = Header(None)) -> Optional[str]:
    """Extract user timezone from header (optional for mood endpoints)"""
    if not x_user_timezone:
        return "UTC"
    
    # Basic validation - return UTC if invalid
    if len(x_user_timezone) < 3 or '/' not in x_user_timezone:
        return "UTC"
    
    return x_user_timezone

@router.post("/today", response_model=MoodResponse)
async def create_today_mood(
    mood: TodayMoodCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create today's mood entry (allows multiple entries per day, most recent is kept)"""
    try:
        # Always create new mood entry for today (no uniqueness check)
        mood_data = mood.dict()
        entry = await MoodCRUD.create_today_mood_entry(db, mood_data, current_user)
        
        return MoodResponse(
            id=entry.id,
            user_id=entry.user_id,
            date=entry.entry_date,
            happiness=entry.happiness,
            focus=entry.focus,
            stress=entry.stress,
            createdAt=entry.created_at,
            updatedAt=getattr(entry, 'updated_at', None)
        )
        
    except Exception as e:
        logger.error(f"Error creating today's mood entry for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create mood entry"
        )

@router.put("/today", response_model=MoodResponse)
async def update_today_mood(
    mood: TodayMoodUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update today's mood entry"""
    try:
        # Update today's mood entry
        mood_data = mood.dict(exclude_unset=True)
        if not mood_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one field must be provided for update"
            )
        
        updated_entry = await MoodCRUD.update_today_mood_entry(db, mood_data, current_user)
        if not updated_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No mood entry found for today. Use POST /mood/today to create one."
            )
        
        return MoodResponse(
            id=updated_entry.id,
            user_id=updated_entry.user_id,
            date=updated_entry.entry_date,
            happiness=updated_entry.happiness,
            focus=updated_entry.focus,
            stress=updated_entry.stress,
            createdAt=updated_entry.created_at,
            updatedAt=getattr(updated_entry, 'updated_at', None)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating today's mood entry for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update mood entry"
        )

@router.get("/today", response_model=MoodResponse)
async def get_today_mood(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get today's mood entry"""
    try:
        entry = await MoodCRUD.get_today_mood_entry(db, current_user)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No mood entry found for today"
            )
        
        return MoodResponse(
            id=entry.id,
            user_id=entry.user_id,
            date=entry.entry_date,
            happiness=entry.happiness,
            focus=entry.focus,
            stress=entry.stress,
            createdAt=entry.created_at,
            updatedAt=getattr(entry, 'updated_at', None)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting today's mood entry for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve mood entry"
        )

@router.delete("/today", status_code=status.HTTP_204_NO_CONTENT)
async def delete_today_mood(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete today's mood entry"""
    try:
        from app.services.time_service import TimeService
        time_service = TimeService()
        today = time_service.get_user_current_date(current_user)
        
        success = await MoodCRUD.delete_mood_entry(db, today, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No mood entry found for today"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting today's mood entry for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete mood entry"
        )

@router.get("/entries", response_model=List[MoodResponse])
async def get_mood_entries(
    start_date: Optional[str] = Query(None, regex=r'^\d{4}-\d{2}-\d{2}$', description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, regex=r'^\d{4}-\d{2}-\d{2}$', description="End date (YYYY-MM-DD)"),
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM format) - legacy support"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: Optional[str] = Depends(get_user_timezone)
):
    """Get mood entries for the current user with optional date filtering"""
    try:
        # Convert string dates to date objects if provided
        start_date_obj = None
        end_date_obj = None
        
        if start_date:
            try:
                start_date_obj = date.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid start_date format. Use YYYY-MM-DD"
                )
        
        if end_date:
            try:
                end_date_obj = date.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid end_date format. Use YYYY-MM-DD"
                )
        
        # Validate date range
        if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_date must be before or equal to end_date"
            )
        
        entries = await MoodCRUD.get_mood_entries(
            db, current_user.id, start_date_obj, end_date_obj, month
        )
        
        # Convert to response format
        return [
            MoodResponse(
                id=entry.id,
                user_id=entry.user_id,
                date=entry.entry_date,
                happiness=entry.happiness,
                focus=entry.focus,
                stress=entry.stress,
                createdAt=entry.created_at,
                updatedAt=getattr(entry, 'updated_at', None)
            )
            for entry in entries
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting mood entries for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve mood entries"
        )

@router.get("/entries/{entry_date}", response_model=MoodResponse)
async def get_mood_entry(
    entry_date: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: Optional[str] = Depends(get_user_timezone)
):
    """Get mood entry for a specific date"""
    import time
    start_time = time.time()
    logger.info(f"😊 [MOOD START] User {current_user.id} getting mood entry for {entry_date}")

    try:
        # Validate and parse date
        try:
            date_obj = date.fromisoformat(entry_date)
        except ValueError:
            logger.warning(f"❌ [MOOD INVALID DATE] Invalid date format: {entry_date}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )

        db_start = time.time()
        entry = await MoodCRUD.get_mood_entry(db, current_user.id, date_obj)
        db_duration = time.time() - db_start
        logger.info(f"😊 [MOOD DB] Database query completed in {db_duration:.2f}s, entry={'found' if entry else 'not found'}")

        if not entry:
            logger.info(f"😊 [MOOD NOT FOUND] No mood entry for {entry_date}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No mood entry found for this date"
            )

        total_duration = time.time() - start_time
        logger.info(f"✅ [MOOD SUCCESS] Mood entry returned in {total_duration:.2f}s")

        return MoodResponse(
            id=entry.id,
            user_id=entry.user_id,
            date=entry.entry_date,
            happiness=entry.happiness,
            focus=entry.focus,
            stress=entry.stress,
            createdAt=entry.created_at,
            updatedAt=getattr(entry, 'updated_at', None)
        )

    except HTTPException:
        raise
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"❌ [MOOD EXCEPTION] Error after {total_duration:.2f}s getting mood entry for date {entry_date}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve mood entry"
        )

# Legacy endpoint for backward compatibility
@router.get("/", response_model=List[MoodResponse])
async def get_mood_entries_legacy(
    start_date: Optional[date] = Query(None, alias="startDate", description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, alias="endDate", description="End date for filtering (YYYY-MM-DD)"),
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM format) - legacy support"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get mood entries for the current user with optional date filtering - Legacy endpoint"""
    entries = await MoodCRUD.get_mood_entries(db, current_user.id, start_date, end_date, month)
    
    # Convert to response format
    return [
        MoodResponse(
            id=entry.id,
            user_id=entry.user_id,
            date=entry.entry_date,
            happiness=entry.happiness,
            focus=entry.focus,
            stress=entry.stress,
            createdAt=entry.created_at,
            updatedAt=getattr(entry, 'updated_at', None)
        )
        for entry in entries
    ]

@router.get("/{entry_date}", response_model=MoodResponse)
async def get_mood_entry_legacy(
    entry_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get mood entry for a specific date - Legacy endpoint"""
    entry = await MoodCRUD.get_mood_entry(db, current_user.id, entry_date)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No mood entry found for this date"
        )
    
    return MoodResponse(
        id=entry.id,
        user_id=entry.user_id,
        date=entry.entry_date,
        happiness=entry.happiness,
        focus=entry.focus,
        stress=entry.stress,
        createdAt=entry.created_at,
        updatedAt=getattr(entry, 'updated_at', None)
    )

@router.post("/", response_model=MoodResponse)
async def create_mood_entry(
    mood: MoodCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create or update a mood entry (upsert) - Legacy endpoint"""
    try:
        entry = await MoodCRUD.upsert_mood_entry(db, mood, current_user.id)
        return MoodResponse(
            id=entry.id,
            user_id=entry.user_id,
            date=entry.entry_date,
            happiness=entry.happiness,
            focus=entry.focus,
            stress=entry.stress,
            createdAt=entry.created_at,
            updatedAt=getattr(entry, 'updated_at', None)
        )
    except Exception as e:
        logger.error(f"Error creating mood entry: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create mood entry: {str(e)}"
        )

@router.put("/{entry_date}", response_model=MoodResponse)
async def update_mood_entry(
    entry_date: date,
    mood: MoodUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a mood entry for a specific date"""
    updated_entry = await MoodCRUD.update_mood_entry(db, entry_date, mood, current_user.id)
    if not updated_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood entry not found for this date"
        )
    
    return MoodResponse(
        id=updated_entry.id,
        user_id=updated_entry.user_id,
        date=updated_entry.entry_date,
        happiness=updated_entry.happiness,
        focus=updated_entry.focus,
        stress=updated_entry.stress,
        createdAt=updated_entry.created_at,
        updatedAt=getattr(updated_entry, 'updated_at', None)
    )

@router.delete("/{entry_date}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mood_entry(
    entry_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a mood entry for a specific date"""
    success = await MoodCRUD.delete_mood_entry(db, entry_date, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood entry not found for this date"
        ) 