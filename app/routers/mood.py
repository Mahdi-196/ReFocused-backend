from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
import logging

from app.db.database import get_db
from app.core.auth import get_current_user
from app.crud.mood import MoodCRUD
from app.schemas.mood import MoodCreate, MoodUpdate, MoodResponse
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
                satisfaction=entry.satisfaction,
                stress=entry.stress,
                dayRating=getattr(entry, 'day_rating', 3),
                notes=getattr(entry, 'note', ''),
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
    try:
        # Validate and parse date
        try:
            date_obj = date.fromisoformat(entry_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        entry = await MoodCRUD.get_mood_entry(db, current_user.id, date_obj)
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
            satisfaction=entry.satisfaction,
            stress=entry.stress,
            dayRating=getattr(entry, 'day_rating', 3),
            notes=getattr(entry, 'note', ''),
            createdAt=entry.created_at,
            updatedAt=getattr(entry, 'updated_at', None)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting mood entry for date {entry_date}: {str(e)}")
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
            satisfaction=entry.satisfaction,
            stress=entry.stress,
            day_rating=getattr(entry, 'day_rating', 3),
            note=getattr(entry, 'note', ''),
            created_at=entry.created_at,
            updated_at=getattr(entry, 'updated_at', None)
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
        satisfaction=entry.satisfaction,
        stress=entry.stress,
        day_rating=getattr(entry, 'day_rating', 3),
        note=getattr(entry, 'note', ''),
        created_at=entry.created_at,
        updated_at=getattr(entry, 'updated_at', None)
    )

@router.post("/", response_model=MoodResponse)
async def create_mood_entry(
    mood: MoodCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create or update a mood entry (upsert)"""
    try:
        entry = await MoodCRUD.upsert_mood_entry(db, mood, current_user.id)
        return MoodResponse(
            id=entry.id,
            user_id=entry.user_id,
            date=entry.entry_date,
            happiness=entry.happiness,
            satisfaction=entry.satisfaction,
            stress=entry.stress,
            day_rating=getattr(entry, 'day_rating', 3),
            note=getattr(entry, 'note', ''),
            created_at=entry.created_at,
            updated_at=getattr(entry, 'updated_at', None)
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
        satisfaction=updated_entry.satisfaction,
        stress=updated_entry.stress,
        day_rating=getattr(updated_entry, 'day_rating', 3),
        note=getattr(updated_entry, 'note', ''),
        created_at=updated_entry.created_at,
        updated_at=getattr(updated_entry, 'updated_at', None)
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