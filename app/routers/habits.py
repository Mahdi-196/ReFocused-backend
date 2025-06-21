from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

from app.db.database import get_db
from app.core.auth import get_current_user
from app.crud.habit import HabitCRUD
from app.schemas.habit import HabitCreate, HabitUpdate, HabitResponse, HabitCompletionUpdate
from app.db.models import User

router = APIRouter()

@router.get("", response_model=List[HabitResponse])
async def get_habits(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all habits for the current user"""
    habits = await HabitCRUD.get_habits(db, current_user.id)
    return habits

@router.post("", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
async def create_habit(
    habit: HabitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new habit"""
    try:
        return await HabitCRUD.create_habit(db, habit, current_user.id)
    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A habit with this name already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create habit"
        )

@router.get("/{habit_id}", response_model=HabitResponse)
async def get_habit(
    habit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific habit by ID"""
    habit = await HabitCRUD.get_habit(db, habit_id, current_user.id)
    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )
    return habit

@router.put("/{habit_id}", response_model=HabitResponse)
async def update_habit(
    habit_id: int,
    habit: HabitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a habit"""
    updated_habit = await HabitCRUD.update_habit(db, habit_id, habit, current_user.id)
    if not updated_habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )
    return updated_habit

@router.post("/completions", status_code=status.HTTP_200_OK)
async def update_habit_completion(
    completion_data: HabitCompletionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a habit as complete or incomplete for a specific date."""
    success = await HabitCRUD.update_completion(
        db,
        habit_id=completion_data.habit_id,
        user_id=current_user.id,
        completion_date=completion_data.date,
        completed=completion_data.completed
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found or completion update failed."
        )
    return {"message": "Habit completion updated successfully."}

@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(
    habit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a habit"""
    success = await HabitCRUD.delete_habit(db, habit_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )

@router.post("/{habit_id}/complete/{completion_date}", status_code=status.HTTP_200_OK)
async def mark_habit_complete(
    habit_id: int,
    completion_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a habit as complete for a specific date"""
    success = await HabitCRUD.mark_habit_complete(db, habit_id, current_user.id, completion_date)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )
    return {"message": "Habit marked as complete"}

@router.delete("/{habit_id}/complete/{completion_date}", status_code=status.HTTP_200_OK)
async def unmark_habit_complete(
    habit_id: int,
    completion_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unmark a habit completion for a specific date"""
    success = await HabitCRUD.unmark_habit_complete(db, habit_id, current_user.id, completion_date)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )
    return {"message": "Habit completion removed"}

@router.get("/{habit_id}/completions")
async def get_habit_completions(
    habit_id: int,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get habit completion dates for a date range"""
    completions = await HabitCRUD.get_habit_completions(
        db, habit_id, current_user.id, start_date, end_date
    )
    return {"dates": completions}

@router.get("/{habit_id}/debug")
async def debug_habit_streak(
    habit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Debug endpoint to troubleshoot streak calculation"""
    from app.core.config import settings
    from sqlalchemy import select, desc
    from app.db.models import HabitStreak
    
    # Get habit
    habit = await HabitCRUD.get_habit(db, habit_id, current_user.id)
    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )
    
    # Get all completions for this habit
    result = await db.execute(
        select(HabitStreak.date).where(HabitStreak.habit_id == habit_id).order_by(desc(HabitStreak.date))
    )
    completion_dates = result.scalars().all()
    
    # Current date info
    current_date = settings.get_current_date()
    
    return {
        "habit_id": habit_id,
        "habit_name": habit.name,
        "stored_streak": habit.streak,
        "current_date": current_date,
        "mock_date_enabled": settings.MOCK_DATE_ENABLED,
        "mock_date": settings.MOCK_DATE,
        "completion_dates": [str(d) for d in completion_dates],
        "completion_count": len(completion_dates),
        "last_completion": str(completion_dates[0]) if completion_dates else None,
        "recalculated_streak": await HabitCRUD._calculate_streak(db, habit_id)
    } 