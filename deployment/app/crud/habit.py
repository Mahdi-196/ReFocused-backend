from typing import List, Optional, Tuple
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, timedelta
from fastapi import HTTPException, status
import pytz
import logging

from app.db.models import Habit, HabitCompletion, User
from app.schemas.habit import HabitCreate, HabitUpdate, HabitStatsResponse
from app.services.time_service import TimeService

logger = logging.getLogger(__name__)

FAVORITE_HABITS_LIMIT = 3

class HabitCRUD:
    """
    Production-ready timezone-aware habit tracking with on-demand reset logic.
    
    Core principles:
    1. All database operations in UTC
    2. On-demand reset check on every read operation
    3. User's local date for all habit logic
    4. Atomic transactions for consistency
    """
    
    def __init__(self):
        self.time_service = TimeService()
    
    async def get_habits_with_reset_check(
        self, 
        db: AsyncSession, 
        user: User,
        include_inactive: bool = False
    ) -> List[Habit]:
        """
        Get all habits with automatic on-demand reset check.
        This is the core method implementing the on-demand reset strategy.
        """
        try:
            # Build query with user's preferences
            query = select(Habit).where(Habit.user_id == user.id)
            
            if not include_inactive:
                query = query.where(Habit.is_active == True)
            
            # Order by favorite first, then by name
            query = query.order_by(Habit.is_favorite.desc(), Habit.name)
            
            result = await db.execute(query)
            habits = list(result.scalars().all())
            
            # Get current date in user's timezone
            current_user_date = self.time_service.get_user_current_date(user)
            
            # Process each habit with reset check
            for habit in habits:
                await self._perform_reset_check(db, habit, user, current_user_date)
                # Set last completed date for frontend
                habit.last_completed_date = await self._get_last_completed_date(db, habit.id)
            
            await db.commit()
            return habits
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error in get_habits_with_reset_check for user {user.id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve habits"
            )
    
    async def get_habit_with_reset_check(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        user: User
    ) -> Optional[Habit]:
        """Get a specific habit with reset check"""
        try:
            result = await db.execute(
                select(Habit).where(
                    and_(Habit.id == habit_id, Habit.user_id == user.id)
                )
            )
            habit = result.scalar_one_or_none()
            
            if not habit:
                return None
            
            # Perform reset check
            current_user_date = self.time_service.get_user_current_date(user)
            await self._perform_reset_check(db, habit, user, current_user_date)
            
            # Set last completed date
            habit.last_completed_date = await self._get_last_completed_date(db, habit.id)
            
            await db.commit()
            return habit
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error in get_habit_with_reset_check: {str(e)}")
            raise
    
    async def create_habit(
        self, 
        db: AsyncSession, 
        habit_data: HabitCreate, 
        user: User
    ) -> Habit:
        """Create a new habit with comprehensive validation"""
        try:
            # Validate and clean name
            cleaned_name = habit_data.name.strip()
            if not cleaned_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Habit name cannot be empty"
                )
            
            # Check for duplicate name
            await self._validate_habit_name_unique(db, user.id, cleaned_name)
            
            # Check favorite limit if trying to create as favorite
            if habit_data.is_favorite:
                await self._check_favorite_limit(db, user.id)
            
            # Create new habit with explicit timestamps
            now_utc = datetime.now(pytz.UTC)
            db_habit = Habit(
                user_id=user.id,
                name=cleaned_name,
                is_favorite=habit_data.is_favorite or False,
                is_active=habit_data.is_active if habit_data.is_active is not None else True,
                streak=0,
                created_at=now_utc,
                last_updated_utc=now_utc
            )
            
            db.add(db_habit)
            await db.commit()
            await db.refresh(db_habit)
            
            return db_habit
            
        except HTTPException:
            # Re-raise HTTP exceptions (our custom validation errors)
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            # Handle database constraint violations
            error_str = str(e).lower()
            if "unique constraint" in error_str or "uix_user_habit_name" in error_str:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A habit with this name already exists"
                )
            elif "check constraint" in error_str or "chk_habit_name_not_empty" in error_str:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Habit name cannot be empty"
                )
            logger.error(f"Error creating habit: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create habit"
            )
    
    async def update_habit(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        habit_data: HabitUpdate, 
        user: User
    ) -> Optional[Habit]:
        """Update a habit with comprehensive validation"""
        try:
            # Get existing habit
            result = await db.execute(
                select(Habit).where(
                    and_(Habit.id == habit_id, Habit.user_id == user.id)
                )
            )
            db_habit = result.scalar_one_or_none()
            
            if not db_habit:
                return None
            
            # Validate name if provided
            if habit_data.name is not None:
                cleaned_name = habit_data.name.strip()
                if not cleaned_name:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Habit name cannot be empty"
                    )
                
                # Check for duplicate name (excluding current habit)
                await self._validate_habit_name_unique(db, user.id, cleaned_name, exclude_habit_id=habit_id)
                db_habit.name = cleaned_name
            
            # Check favorite limit if trying to set as favorite
            if habit_data.is_favorite is not None:
                if habit_data.is_favorite and not db_habit.is_favorite:
                    # User wants to favorite - check limit
                    await self._check_favorite_limit(db, user.id, exclude_habit_id=habit_id)
                db_habit.is_favorite = habit_data.is_favorite
            
            # Update is_active if provided
            if habit_data.is_active is not None:
                db_habit.is_active = habit_data.is_active
            
            # Update last_updated_utc
            db_habit.last_updated_utc = datetime.now(pytz.UTC)
            
            await db.commit()
            await db.refresh(db_habit)
            
            # Set last completed date
            db_habit.last_completed_date = await self._get_last_completed_date(db, habit_id)
            
            return db_habit
            
        except HTTPException:
            # Re-raise HTTP exceptions (our custom validation errors)
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            # Handle database constraint violations
            error_str = str(e).lower()
            if "unique constraint" in error_str or "uix_user_habit_name" in error_str:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A habit with this name already exists"
                )
            elif "check constraint" in error_str or "chk_habit_name_not_empty" in error_str:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Habit name cannot be empty"
                )
            logger.error(f"Error updating habit {habit_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update habit"
            )
    
    async def delete_habit(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        user: User
    ) -> bool:
        """Delete a habit and all its completions"""
        try:
            result = await db.execute(
                select(Habit).where(
                    and_(Habit.id == habit_id, Habit.user_id == user.id)
                )
            )
            db_habit = result.scalar_one_or_none()
            
            if not db_habit:
                return False
            
            await db.delete(db_habit)
            await db.commit()
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting habit {habit_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete habit"
            )
    
    async def mark_habit_completion(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        completion_date: date, 
        completed: bool, 
        user: User
    ) -> bool:
        """
        Mark habit completion for a specific date with timezone awareness.
        Implements atomic completion tracking with streak recalculation.
        """
        try:
            # Verify habit belongs to user
            habit_result = await db.execute(
                select(Habit).where(
                    and_(Habit.id == habit_id, Habit.user_id == user.id)
                )
            )
            habit = habit_result.scalar_one_or_none()
            if not habit:
                return False
            
            # Check for existing completion
            completion_result = await db.execute(
                select(HabitCompletion).where(
                    and_(
                        HabitCompletion.habit_id == habit_id,
                        HabitCompletion.date == completion_date
                    )
                )
            )
            existing_completion = completion_result.scalar_one_or_none()
            
            completion_changed = False
            
            if completed and not existing_completion:
                # Create new completion
                new_completion = HabitCompletion(
                    habit_id=habit_id,
                    user_id=user.id,
                    date=completion_date,
                    completed=True,
                    timezone=user.timezone
                )
                db.add(new_completion)
                completion_changed = True
                
            elif not completed and existing_completion:
                # Remove existing completion
                await db.delete(existing_completion)
                completion_changed = True
                
            elif existing_completion and existing_completion.completed != completed:
                # Update existing completion
                existing_completion.completed = completed
                existing_completion.completed_at = datetime.now(pytz.UTC)
                completion_changed = True
            
            # Only recalculate streak if completion actually changed
            if completion_changed:
                # Recalculate streak after the completion change
                await self._recalculate_habit_streak(db, habit_id, user)
            
            # Update habit's last_updated_utc to current time
            habit.last_updated_utc = datetime.now(pytz.UTC)
            
            await db.commit()
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error marking habit completion: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update habit completion"
            )
    
    async def get_habit_completions(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        start_date: date, 
        end_date: date, 
        user: User
    ) -> List[HabitCompletion]:
        """Get completions for a specific habit within date range"""
        # Verify habit ownership
        habit_result = await db.execute(
            select(Habit).where(
                and_(Habit.id == habit_id, Habit.user_id == user.id)
            )
        )
        habit = habit_result.scalar_one_or_none()
        if not habit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habit not found"
            )
        
        # Get completions
        result = await db.execute(
            select(HabitCompletion).where(
                and_(
                    HabitCompletion.habit_id == habit_id,
                    HabitCompletion.date >= start_date,
                    HabitCompletion.date <= end_date,
                    HabitCompletion.completed == True
                )
            ).order_by(HabitCompletion.date.desc())
        )
        return result.scalars().all()
    
    async def get_completions_for_range(
        self, 
        db: AsyncSession, 
        user: User, 
        start_date: date, 
        end_date: date
    ) -> List[HabitCompletion]:
        """Get all habit completions for all user's habits within date range"""
        # Get all user's habits
        habits_result = await db.execute(
            select(Habit.id).where(Habit.user_id == user.id)
        )
        habit_ids = [row[0] for row in habits_result.fetchall()]
        
        if not habit_ids:
            return []
        
        # Get all completions for the user's habits in the date range
        result = await db.execute(
            select(HabitCompletion).where(
                and_(
                    HabitCompletion.habit_id.in_(habit_ids),
                    HabitCompletion.date >= start_date,
                    HabitCompletion.date <= end_date,
                    HabitCompletion.completed == True
                )
            ).order_by(HabitCompletion.date.desc(), HabitCompletion.habit_id)
        )
        return result.scalars().all()
    
    async def get_habit_stats(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        user: User
    ) -> HabitStatsResponse:
        """Get comprehensive habit statistics"""
        try:
            # Verify habit exists and get current streak
            habit = await self.get_habit_with_reset_check(db, habit_id, user)
            if not habit:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Habit not found"
                )
            
            # Get completion statistics
            current_date = self.time_service.get_user_current_date(user)
            seven_days_ago = current_date - timedelta(days=7)
            thirty_days_ago = current_date - timedelta(days=30)
            
            # Total completions
            total_result = await db.execute(
                select(func.count(HabitCompletion.id)).where(
                    and_(
                        HabitCompletion.habit_id == habit_id,
                        HabitCompletion.completed == True
                    )
                )
            )
            total_completions = total_result.scalar() or 0
            
            # 7-day completion rate
            seven_day_result = await db.execute(
                select(func.count(HabitCompletion.id)).where(
                    and_(
                        HabitCompletion.habit_id == habit_id,
                        HabitCompletion.date >= seven_days_ago,
                        HabitCompletion.date <= current_date,
                        HabitCompletion.completed == True
                    )
                )
            )
            seven_day_completions = seven_day_result.scalar() or 0
            completion_rate_7days = (seven_day_completions / 7) * 100
            
            # 30-day completion rate
            thirty_day_result = await db.execute(
                select(func.count(HabitCompletion.id)).where(
                    and_(
                        HabitCompletion.habit_id == habit_id,
                        HabitCompletion.date >= thirty_days_ago,
                        HabitCompletion.date <= current_date,
                        HabitCompletion.completed == True
                    )
                )
            )
            thirty_day_completions = thirty_day_result.scalar() or 0
            completion_rate_30days = (thirty_day_completions / 30) * 100
            
            # Last completed date
            last_completed_result = await db.execute(
                select(HabitCompletion.date).where(
                    and_(
                        HabitCompletion.habit_id == habit_id,
                        HabitCompletion.completed == True
                    )
                ).order_by(HabitCompletion.date.desc()).limit(1)
            )
            last_completed = last_completed_result.scalar_one_or_none()
            
            # Calculate longest streak (this is expensive but accurate)
            longest_streak = await self._calculate_longest_streak(db, habit_id)
            
            return HabitStatsResponse(
                habit_id=habit_id,
                total_completions=total_completions,
                current_streak=habit.streak,
                longest_streak=longest_streak,
                completion_rate_7days=round(completion_rate_7days, 1),
                completion_rate_30days=round(completion_rate_30days, 1),
                last_completed=last_completed
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting habit stats: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve habit statistics"
            )
    
    # Private helper methods
    async def _perform_reset_check(
        self, 
        db: AsyncSession, 
        habit: Habit, 
        user: User, 
        current_user_date: date
    ) -> None:
        """
        Perform on-demand reset check for a habit.
        This is the core implementation of the on-demand reset strategy.
        """
        if not habit.last_updated_utc:
            # If habit has never been updated, just recalculate streak
            await self._recalculate_habit_streak(db, habit.id, user)
            habit.last_updated_utc = datetime.now(pytz.UTC)
            return
        
        # Convert last update time to user's timezone and get date
        last_updated_user_tz = self.time_service.convert_to_user_timezone(
            habit.last_updated_utc, user
        )
        last_updated_date = last_updated_user_tz.date()
        
        # Check if day has changed in user's timezone
        days_since_update = (current_user_date - last_updated_date).days
        
        if days_since_update > 0:
            # Only perform day change logic if it's been more than a day since update
            # and only if the gap is significant (more than 1 day) to avoid
            # unnecessary resets during normal daily progression
            if days_since_update >= 1:
                await self._handle_day_change(db, habit, user, last_updated_date, current_user_date)
            
            # Always update the last_updated_utc to current time
            habit.last_updated_utc = datetime.now(pytz.UTC)
    
    async def _handle_day_change(
        self, 
        db: AsyncSession, 
        habit: Habit, 
        user: User,
        old_date: date, 
        new_date: date
    ) -> None:
        """Handle when a habit crosses into a new day"""
        days_missed = (new_date - old_date).days
        
        # For small day gaps (1-2 days), check completion history
        # For larger gaps, always recalculate from scratch
        if days_missed <= 2:
            # Check if the previous day was completed
            yesterday = new_date - timedelta(days=1)
            yesterday_completed = await self._check_date_completed(db, habit.id, yesterday)
            
            if not yesterday_completed:
                # Yesterday was not completed, but we need to recalculate the streak
                # instead of just resetting to 0, as there might be a longer streak
                await self._recalculate_habit_streak(db, habit.id, user)
            # If yesterday was completed, leave the streak as is and let
            # the completion tracking increment it properly
        else:
            # Multiple days missed - recalculate streak from scratch
            # Don't just reset to 0, as the user might have a current streak
            await self._recalculate_habit_streak(db, habit.id, user)
    
    async def _recalculate_habit_streak(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        user: User
    ) -> int:
        """Recalculate habit streak from completions"""
        try:
            current_date = self.time_service.get_user_current_date(user)
            streak = 0
            check_date = current_date
            
            # Count backwards from today until we find a gap
            while True:
                completed = await self._check_date_completed(db, habit_id, check_date)
                if not completed:
                    break
                streak += 1
                check_date -= timedelta(days=1)
                
                # Safety limit to prevent infinite loops
                if streak > 1000:
                    break
            
            # Update habit streak - get fresh habit object to avoid stale data
            habit_result = await db.execute(
                select(Habit).where(Habit.id == habit_id)
            )
            habit = habit_result.scalar_one_or_none()
            if habit:
                old_streak = habit.streak
                habit.streak = streak
                logger.info(f"Updated habit {habit_id} streak from {old_streak} to {streak}")
            
            return streak
            
        except Exception as e:
            logger.error(f"Error recalculating streak for habit {habit_id}: {str(e)}")
            raise
    
    async def _check_date_completed(
        self, 
        db: AsyncSession, 
        habit_id: int, 
        check_date: date
    ) -> bool:
        """Check if a habit was completed on a specific date"""
        result = await db.execute(
            select(HabitCompletion).where(
                and_(
                    HabitCompletion.habit_id == habit_id,
                    HabitCompletion.date == check_date,
                    HabitCompletion.completed == True
                )
            )
        )
        return result.scalar_one_or_none() is not None
    
    async def _get_last_completed_date(
        self, 
        db: AsyncSession, 
        habit_id: int
    ) -> Optional[str]:
        """Get the last completed date as string (YYYY-MM-DD)"""
        result = await db.execute(
            select(HabitCompletion.date).where(
                and_(
                    HabitCompletion.habit_id == habit_id,
                    HabitCompletion.completed == True
                )
            ).order_by(HabitCompletion.date.desc()).limit(1)
        )
        last_date = result.scalar_one_or_none()
        return last_date.strftime("%Y-%m-%d") if last_date else None
    
    async def _check_favorite_limit(
        self, 
        db: AsyncSession, 
        user_id: int, 
        exclude_habit_id: Optional[int] = None
    ) -> None:
        """Check if user has reached favorite habits limit"""
        query = select(func.count(Habit.id)).where(
            and_(
                Habit.user_id == user_id,
                Habit.is_favorite == True,
                Habit.is_active == True  # Only count active habits
            )
        )
        
        if exclude_habit_id:
            query = query.where(Habit.id != exclude_habit_id)
        
        result = await db.execute(query)
        favorite_count = result.scalar()
        
        if favorite_count >= FAVORITE_HABITS_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {FAVORITE_HABITS_LIMIT} habits can be pinned. Unpin another habit first."
            )
    
    async def _validate_habit_name_unique(
        self,
        db: AsyncSession,
        user_id: int,
        name: str,
        exclude_habit_id: Optional[int] = None
    ) -> None:
        """Validate habit name is unique for user"""
        query = select(Habit).where(
            and_(
                Habit.user_id == user_id,
                Habit.name == name.strip(),
                Habit.is_active == True  # Only check against active habits
            )
        )
        
        if exclude_habit_id:
            query = query.where(Habit.id != exclude_habit_id)
        
        result = await db.execute(query)
        existing_habit = result.scalar_one_or_none()
        
        if existing_habit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A habit with this name already exists"
            )
    
    async def _calculate_longest_streak(
        self, 
        db: AsyncSession, 
        habit_id: int
    ) -> int:
        """Calculate the longest streak for a habit (expensive operation)"""
        try:
            # Get all completions ordered by date
            result = await db.execute(
                select(HabitCompletion.date).where(
                    and_(
                        HabitCompletion.habit_id == habit_id,
                        HabitCompletion.completed == True
                    )
                ).order_by(HabitCompletion.date.asc())
            )
            completion_dates = [row[0] for row in result.fetchall()]
            
            if not completion_dates:
                return 0
            
            max_streak = 1
            current_streak = 1
            
            for i in range(1, len(completion_dates)):
                if completion_dates[i] == completion_dates[i-1] + timedelta(days=1):
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 1
            
            return max_streak
            
        except Exception as e:
            logger.error(f"Error calculating longest streak: {str(e)}")
            return 0

# Global instance
habit_crud = HabitCRUD() 