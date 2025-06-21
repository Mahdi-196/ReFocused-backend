from typing import List, Optional
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from fastapi import HTTPException, status
from app.db.models import Habit, HabitStreak
from app.schemas.habit import HabitCreate, HabitUpdate
from app.core.config import settings

FAVORITE_HABITS_LIMIT = 3

class HabitCRUD:
    @staticmethod
    async def get_habits(db: AsyncSession, user_id: int) -> List[Habit]:
        """Get all habits for a user with their stored streaks"""
        result = await db.execute(
            select(Habit).where(Habit.user_id == user_id).order_by(Habit.is_favorite.desc(), Habit.name)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_habit(db: AsyncSession, habit_id: int, user_id: int) -> Optional[Habit]:
        """Get a specific habit by ID and user, with its stored streak"""
        result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_habit(db: AsyncSession, habit: HabitCreate, user_id: int) -> Habit:
        """Create a new habit for a user"""
        db_habit = Habit(
            user_id=user_id,
            name=habit.name,
            is_favorite=habit.is_favorite or False
        )
        db.add(db_habit)
        await db.commit()
        await db.refresh(db_habit)
        
        # Set initial streak to 0
        db_habit.streak = 0
        return db_habit
    
    @staticmethod
    async def update_habit(db: AsyncSession, habit_id: int, habit: HabitUpdate, user_id: int) -> Optional[Habit]:
        """Update a habit"""
        # If trying to favorite, check the limit
        if habit.is_favorite:
            fovorites_count_result = await db.execute(
                select(func.count(Habit.id)).where(
                    and_(
                        Habit.user_id == user_id,
                        Habit.is_favorite == True,
                        Habit.id != habit_id
                    )
                )
            )
            
            if fovorites_count_result.scalar() >= FAVORITE_HABITS_LIMIT:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"You can only have up to {FAVORITE_HABITS_LIMIT} favorite habits."
                )

        result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        db_habit = result.scalar_one_or_none()
        
        if not db_habit:
            return None
        
        update_data = habit.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_habit, field, value)
        
        await db.commit()
        await db.refresh(db_habit)
        
        # Calculate current streak
        db_habit.streak = await HabitCRUD._calculate_streak(db, db_habit.id)
        return db_habit
    
    @staticmethod
    async def update_completion(db: AsyncSession, habit_id: int, user_id: int, completion_date: date, completed: bool) -> bool:
        """Mark a habit as complete or incomplete for a date and update streak."""
        # Verify habit belongs to user
        habit_result = await db.execute(select(Habit).where(and_(Habit.id == habit_id, Habit.user_id == user_id)))
        habit = habit_result.scalar_one_or_none()
        if not habit:
            return False

        # Find existing completion record
        completion_result = await db.execute(select(HabitStreak).where(and_(HabitStreak.habit_id == habit_id, HabitStreak.date == completion_date)))
        existing_completion = completion_result.scalar_one_or_none()

        change_made = False
        if completed and not existing_completion:
            # Add completion
            new_completion = HabitStreak(habit_id=habit_id, date=completion_date)
            db.add(new_completion)
            change_made = True
        elif not completed and existing_completion:
            # Remove completion
            await db.delete(existing_completion)
            change_made = True

        if change_made:
            await db.flush()

        # Recalculate and update the streak for the habit
        new_streak = await HabitCRUD._calculate_streak(db, habit_id)
        if habit.streak != new_streak:
            habit.streak = new_streak
        
        await db.commit()
        return True

    @staticmethod
    async def delete_habit(db: AsyncSession, habit_id: int, user_id: int) -> bool:
        """Delete a habit"""
        result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        db_habit = result.scalar_one_or_none()
        
        if not db_habit:
            return False
        
        await db.delete(db_habit)
        await db.commit()
        return True
    
    @staticmethod
    async def mark_habit_complete(db: AsyncSession, habit_id: int, user_id: int, completion_date: date) -> bool:
        """Mark a habit as complete for a specific date"""
        return await HabitCRUD.update_completion(db, habit_id, user_id, completion_date, completed=True)
    
    @staticmethod
    async def unmark_habit_complete(db: AsyncSession, habit_id: int, user_id: int, completion_date: date) -> bool:
        """Unmark a habit completion for a specific date"""
        return await HabitCRUD.update_completion(db, habit_id, user_id, completion_date, completed=False)
    
    @staticmethod
    async def get_habit_completions(db: AsyncSession, habit_id: int, user_id: int, start_date: date, end_date: date) -> List[date]:
        """Get habit completion dates for a date range"""
        # Verify habit belongs to user
        result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        habit = result.scalar_one_or_none()
        
        if not habit:
            return []
        
        result = await db.execute(
            select(HabitStreak.date).where(
                and_(
                    HabitStreak.habit_id == habit_id,
                    HabitStreak.date >= start_date,
                    HabitStreak.date <= end_date
                )
            ).order_by(HabitStreak.date)
        )
        
        return result.scalars().all()
    
    @staticmethod
    async def _calculate_streak(db: AsyncSession, habit_id: int) -> int:
        """Calculate current streak for a habit."""
        result = await db.execute(
            select(HabitStreak.date).where(HabitStreak.habit_id == habit_id).order_by(desc(HabitStreak.date))
        )
        completion_dates = result.scalars().all()

        if not completion_dates:
            return 0

        last_completion = completion_dates[0]
        today = settings.get_current_date()  # Use configurable date for testing

        if last_completion < today - timedelta(days=1):
            return 0

        streak = 0
        expected_date = today if last_completion == today else today - timedelta(days=1)

        for completion_date in completion_dates:
            if completion_date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif completion_date < expected_date:
                break
        
        return streak 