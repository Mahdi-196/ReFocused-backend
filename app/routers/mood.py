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
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM format)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get mood entries for the current user, optionally filtered by month"""
    entries = await MoodCRUD.get_mood_entries(db, current_user.id, month)
    # Convert to response format
    return [
        MoodResponse(
            id=entry.id,
            happiness=entry.happiness,
            satisfaction=entry.satisfaction,
            stress=entry.stress,
            day_rating=entry.day_rating,
            note=entry.note,
            date=entry.entry_date,
            created_at=entry.created_at
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
            detail="Mood entry not found for this date"
        )
    
    return MoodResponse(
        id=entry.id,
        happiness=entry.happiness,
        satisfaction=entry.satisfaction,
        stress=entry.stress,
        day_rating=entry.day_rating,
        note=entry.note,
        date=entry.entry_date,
        created_at=entry.created_at
    )

@router.post("/", response_model=MoodResponse, status_code=status.HTTP_201_CREATED)
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
            happiness=entry.happiness,
            satisfaction=entry.satisfaction,
            stress=entry.stress,
            day_rating=entry.day_rating,
            note=entry.note,
            date=entry.entry_date,
            created_at=entry.created_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create mood entry"
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
        happiness=updated_entry.happiness,
        satisfaction=updated_entry.satisfaction,
        stress=updated_entry.stress,
        day_rating=updated_entry.day_rating,
        note=updated_entry.note,
        date=updated_entry.entry_date,
        created_at=updated_entry.created_at
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