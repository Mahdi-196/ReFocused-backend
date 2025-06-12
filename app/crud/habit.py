from typing import List, Optional
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from app.db.models import Habit, HabitStreak
from app.schemas.habit import HabitCreate, HabitUpdate

class HabitCRUD:
    @staticmethod
    async def get_habits(db: AsyncSession, user_id: int) -> List[Habit]:
        """Get all habits for a user with calculated streaks"""
        result = await db.execute(
            select(Habit).where(Habit.user_id == user_id).order_by(Habit.name)
        )
        habits = result.scalars().all()
        
        # Calculate current streaks for each habit
        for habit in habits:
            habit.streak = await HabitCRUD._calculate_streak(db, habit.id)
        
        return habits
    
    @staticmethod
    async def get_habit(db: AsyncSession, habit_id: int, user_id: int) -> Optional[Habit]:
        """Get a specific habit by ID and user"""
        result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        habit = result.scalar_one_or_none()
        
        if habit:
            habit.streak = await HabitCRUD._calculate_streak(db, habit.id)
        
        return habit
    
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
        # Verify habit belongs to user
        result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        habit = result.scalar_one_or_none()
        
        if not habit:
            return False
        
        # Check if already completed
        existing = await db.execute(
            select(HabitStreak).where(
                and_(HabitStreak.habit_id == habit_id, HabitStreak.date == completion_date)
            )
        )
        
        if existing.scalar_one_or_none():
            return True  # Already completed
        
        # Add completion
        streak = HabitStreak(habit_id=habit_id, date=completion_date)
        db.add(streak)
        await db.commit()
        return True
    
    @staticmethod
    async def unmark_habit_complete(db: AsyncSession, habit_id: int, user_id: int, completion_date: date) -> bool:
        """Unmark a habit completion for a specific date"""
        # Verify habit belongs to user
        result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        habit = result.scalar_one_or_none()
        
        if not habit:
            return False
        
        # Remove completion
        result = await db.execute(
            select(HabitStreak).where(
                and_(HabitStreak.habit_id == habit_id, HabitStreak.date == completion_date)
            )
        )
        streak = result.scalar_one_or_none()
        
        if streak:
            await db.delete(streak)
            await db.commit()
        
        return True
    
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
        """Calculate current streak for a habit"""
        # Get all completion dates for this habit, ordered by date descending
        result = await db.execute(
            select(HabitStreak.date).where(
                HabitStreak.habit_id == habit_id
            ).order_by(desc(HabitStreak.date))
        )
        completion_dates = result.scalars().all()
        
        if not completion_dates:
            return 0
        
        # Calculate consecutive days from today backwards
        today = date.today()
        streak = 0
        current_date = today
        
        # Check if today is completed, if not start from yesterday
        if completion_dates and completion_dates[0] == today:
            streak = 1
            current_date = today - timedelta(days=1)
        elif completion_dates and completion_dates[0] == today - timedelta(days=1):
            # If yesterday was completed but not today, start streak from yesterday
            streak = 1
            current_date = today - timedelta(days=2)
        else:
            # No recent completions
            return 0
        
        # Count consecutive days backwards
        for completion_date in completion_dates[1:]:
            if completion_date == current_date:
                streak += 1
                current_date -= timedelta(days=1)
            else:
                break
        
        return streak 