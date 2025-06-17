from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

from app.db.database import get_db
from app.core.auth import get_current_user
from app.crud.mood import MoodCRUD
from app.schemas.mood import MoodCreate, MoodUpdate, MoodResponse
from app.db.models import User

router = APIRouter()

@router.get("/", response_model=List[MoodResponse])
async def get_mood_entries(
    start_date: Optional[date] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for filtering (YYYY-MM-DD)"),
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM format) - legacy support"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get mood entries for the current user with optional date filtering"""
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
            created_at=entry.created_at,
            updated_at=getattr(entry, 'updated_at', None)
        )
        for entry in entries
    ]

@router.get("/{entry_date}", response_model=MoodResponse)
async def get_mood_entry(
    entry_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get mood entry for a specific date"""
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
            created_at=entry.created_at,
            updated_at=getattr(entry, 'updated_at', None)
        )
    except Exception as e:
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