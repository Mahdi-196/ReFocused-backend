from typing import List, Optional, Tuple
from sqlalchemy import select, and_, func, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import date, datetime, timedelta
from fastapi import HTTPException, status
import pytz
import logging

from app.db.models import (
    User, CalendarEntry, CalendarHabitCompletion, CalendarMoodEntry,
    Habit, HabitCompletion, MoodEntry
)
from app.schemas.calendar import (
    CalendarEntryCreate, CalendarEntryUpdate,
    CalendarHabitCompletionCreate, CalendarMoodEntryCreate
)
from app.services.time_service import TimeService

logger = logging.getLogger(__name__)

class CalendarCRUD:
    """
    Calendar CRUD operations with timezone awareness and read-only protection.
    
    Core features:
    1. Timezone-aware date handling
    2. Read-only protection for past dates
    3. Integration with existing habit and mood systems
    4. Historical data preservation
    """
    
    def __init__(self):
        self.time_service = TimeService()
    
    async def get_calendar_entries(
        self, 
        db: AsyncSession, 
        user: User, 
        start_date: date, 
        end_date: date
    ) -> List[CalendarEntry]:
        """Get calendar entries for a date range"""
        try:
            query = (
                select(CalendarEntry)
                .options(
                    selectinload(CalendarEntry.habit_completions),
                    selectinload(CalendarEntry.mood_entry)
                )
                .where(
                    and_(
                        CalendarEntry.user_id == user.id,
                        CalendarEntry.date >= start_date,
                        CalendarEntry.date <= end_date
                    )
                )
                .order_by(CalendarEntry.date.desc())
            )
            
            result = await db.execute(query)
            entries = list(result.scalars().all())
            
            # Update lock status for all entries
            await self._update_lock_status(db, entries, user)
            
            return entries
            
        except Exception as e:
            logger.error(f"Error getting calendar entries for user {user.id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve calendar entries"
            )
    
    async def get_calendar_entry(
        self, 
        db: AsyncSession, 
        user: User, 
        entry_date: date
    ) -> Optional[CalendarEntry]:
        """Get a specific calendar entry by date"""
        try:
            query = (
                select(CalendarEntry)
                .options(
                    selectinload(CalendarEntry.habit_completions),
                    selectinload(CalendarEntry.mood_entry)
                )
                .where(
                    and_(
                        CalendarEntry.user_id == user.id,
                        CalendarEntry.date == entry_date
                    )
                )
            )
            
            result = await db.execute(query)
            entry = result.scalar_one_or_none()
            
            if entry:
                # Update lock status
                await self._update_lock_status(db, [entry], user)
            
            return entry
            
        except Exception as e:
            logger.error(f"Error getting calendar entry for date {entry_date}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve calendar entry"
            )
    
    async def create_calendar_entry(
        self, 
        db: AsyncSession, 
        user: User, 
        entry_data: CalendarEntryCreate
    ) -> CalendarEntry:
        """Create a new calendar entry with habits and mood"""
        try:
            # Check if entry already exists
            existing = await self.get_calendar_entry(db, user, entry_data.date)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Calendar entry for {entry_data.date} already exists"
                )
            
            # Check read-only protection
            current_date = self.time_service.get_user_current_date(user)
            is_locked = entry_data.date < current_date
            
            if is_locked:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot create calendar entries for past dates"
                )
            
            # Create calendar entry
            calendar_entry = CalendarEntry(
                user_id=user.id,
                date=entry_data.date,
                notes=entry_data.notes,
                is_locked=is_locked
            )
            
            db.add(calendar_entry)
            await db.flush()  # Get the ID
            
            # Add habit completions
            if entry_data.habit_completions:
                for habit_completion_data in entry_data.habit_completions:
                    # Get habit details for historical preservation
                    habit = await self._get_habit_details(db, user, habit_completion_data.habit_id, entry_data.date)
                    
                    habit_completion = CalendarHabitCompletion(
                        calendar_entry_id=calendar_entry.id,
                        habit_id=habit_completion_data.habit_id,
                        habit_name=habit.get('name', habit_completion_data.habit_name),
                        completed=habit_completion_data.completed,
                        completed_at=habit_completion_data.completed_at,
                        was_active_on_date=habit.get('was_active', True)
                    )
                    db.add(habit_completion)
            
            # Add mood entry
            if entry_data.mood_entry:
                mood_entry = CalendarMoodEntry(
                    calendar_entry_id=calendar_entry.id,
                    happiness=entry_data.mood_entry.happiness,
                    focus=entry_data.mood_entry.focus,
                    stress=entry_data.mood_entry.stress,
                    day_rating=entry_data.mood_entry.day_rating
                )
                db.add(mood_entry)
            
            await db.commit()
            
            # Refresh to get relationships
            await db.refresh(calendar_entry, [
                'habit_completions', 'mood_entry'
            ])
            
            return calendar_entry
            
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating calendar entry: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create calendar entry"
            )
    
    async def update_calendar_entry(
        self, 
        db: AsyncSession, 
        user: User, 
        entry_date: date, 
        entry_data: CalendarEntryUpdate
    ) -> Optional[CalendarEntry]:
        """Update an existing calendar entry"""
        try:
            # Get existing entry
            calendar_entry = await self.get_calendar_entry(db, user, entry_date)
            if not calendar_entry:
                return None
            
            # Check read-only protection
            if calendar_entry.is_locked:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot modify calendar entries for past dates"
                )
            
            # Update notes
            if entry_data.notes is not None:
                calendar_entry.notes = entry_data.notes
            
            # Update habit completions
            if entry_data.habit_completions is not None:
                # Delete existing habit completions
                await db.execute(
                    delete(CalendarHabitCompletion).where(
                        CalendarHabitCompletion.calendar_entry_id == calendar_entry.id
                    )
                )
                
                # Add new habit completions
                for habit_completion_data in entry_data.habit_completions:
                    habit = await self._get_habit_details(db, user, habit_completion_data.habit_id, entry_date)
                    
                    habit_completion = CalendarHabitCompletion(
                        calendar_entry_id=calendar_entry.id,
                        habit_id=habit_completion_data.habit_id,
                        habit_name=habit.get('name', habit_completion_data.habit_name),
                        completed=habit_completion_data.completed,
                        completed_at=habit_completion_data.completed_at,
                        was_active_on_date=habit.get('was_active', True)
                    )
                    db.add(habit_completion)
            
            # Update mood entry
            if entry_data.mood_entry is not None:
                if calendar_entry.mood_entry:
                    # Update existing
                    calendar_entry.mood_entry.happiness = entry_data.mood_entry.happiness
                    calendar_entry.mood_entry.focus = entry_data.mood_entry.focus
                    calendar_entry.mood_entry.stress = entry_data.mood_entry.stress
                    calendar_entry.mood_entry.day_rating = entry_data.mood_entry.day_rating
                else:
                    # Create new
                    mood_entry = CalendarMoodEntry(
                        calendar_entry_id=calendar_entry.id,
                        happiness=entry_data.mood_entry.happiness,
                        focus=entry_data.mood_entry.focus,
                        stress=entry_data.mood_entry.stress,
                        day_rating=entry_data.mood_entry.day_rating
                    )
                    db.add(mood_entry)
            
            calendar_entry.updated_at = datetime.now(pytz.UTC)
            await db.commit()
            
            # Refresh to get updated relationships
            await db.refresh(calendar_entry, [
                'habit_completions', 'mood_entry'
            ])
            
            return calendar_entry
            
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating calendar entry: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update calendar entry"
            )
    
    async def delete_calendar_entry(
        self, 
        db: AsyncSession, 
        user: User, 
        entry_date: date
    ) -> bool:
        """Delete a calendar entry"""
        try:
            calendar_entry = await self.get_calendar_entry(db, user, entry_date)
            if not calendar_entry:
                return False
            
            # Check read-only protection
            if calendar_entry.is_locked:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot delete calendar entries for past dates"
                )
            
            await db.delete(calendar_entry)
            await db.commit()
            return True
            
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting calendar entry: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete calendar entry"
            )
    
    async def sync_with_existing_data(
        self, 
        db: AsyncSession, 
        user: User, 
        sync_date: date
    ) -> Optional[CalendarEntry]:
        """Sync calendar entry with existing habit completions and mood entries"""
        try:
            # Check if calendar entry exists
            calendar_entry = await self.get_calendar_entry(db, user, sync_date)
            
            # Get existing habit completions for this date
            habit_completions_query = (
                select(HabitCompletion)
                .join(Habit)
                .where(
                    and_(
                        HabitCompletion.user_id == user.id,
                        HabitCompletion.date == sync_date
                    )
                )
                .options(selectinload(HabitCompletion.habit))
            )
            
            habit_completions_result = await db.execute(habit_completions_query)
            habit_completions = list(habit_completions_result.scalars().all())
            
            # Get existing mood entry for this date
            mood_query = select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user.id,
                    MoodEntry.entry_date == sync_date
                )
            )
            mood_result = await db.execute(mood_query)
            mood_entry = mood_result.scalar_one_or_none()
            
            # If no data exists, return None
            if not habit_completions and not mood_entry:
                return None
            
            # Create calendar entry if it doesn't exist
            if not calendar_entry:
                current_date = self.time_service.get_user_current_date(user)
                is_locked = sync_date < current_date
                
                calendar_entry = CalendarEntry(
                    user_id=user.id,
                    date=sync_date,
                    notes=None,
                    is_locked=is_locked
                )
                db.add(calendar_entry)
                await db.flush()
            
            # Sync habit completions
            for completion in habit_completions:
                existing_calendar_completion = await db.execute(
                    select(CalendarHabitCompletion).where(
                        and_(
                            CalendarHabitCompletion.calendar_entry_id == calendar_entry.id,
                            CalendarHabitCompletion.habit_id == completion.habit_id
                        )
                    )
                )
                
                if not existing_calendar_completion.scalar_one_or_none():
                    calendar_habit_completion = CalendarHabitCompletion(
                        calendar_entry_id=calendar_entry.id,
                        habit_id=completion.habit_id,
                        habit_name=completion.habit.name,
                        completed=completion.completed,
                        completed_at=completion.completed_at,
                        was_active_on_date=True
                    )
                    db.add(calendar_habit_completion)
            
            # Sync mood entry
            if mood_entry and not calendar_entry.mood_entry:
                calendar_mood_entry = CalendarMoodEntry(
                    calendar_entry_id=calendar_entry.id,
                    happiness=mood_entry.happiness,
                    focus=mood_entry.focus,
                    stress=mood_entry.stress,
                    day_rating=getattr(mood_entry, 'day_rating', None)
                )
                db.add(calendar_mood_entry)
            
            await db.commit()
            
            # Refresh to get relationships
            await db.refresh(calendar_entry, [
                'habit_completions', 'mood_entry'
            ])
            
            return calendar_entry
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error syncing calendar entry: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to sync calendar entry"
            )
    
    async def _update_lock_status(
        self, 
        db: AsyncSession, 
        entries: List[CalendarEntry], 
        user: User
    ) -> None:
        """Update lock status for calendar entries based on current date"""
        current_date = self.time_service.get_user_current_date(user)
        
        updates_needed = False
        for entry in entries:
            should_be_locked = entry.date < current_date
            if entry.is_locked != should_be_locked:
                entry.is_locked = should_be_locked
                updates_needed = True
        
        if updates_needed:
            await db.commit()
    
    async def _get_habit_details(
        self, 
        db: AsyncSession, 
        user: User, 
        habit_id: int, 
        target_date: date
    ) -> dict:
        """Get habit details with historical context"""
        try:
            query = select(Habit).where(
                and_(
                    Habit.id == habit_id,
                    Habit.user_id == user.id
                )
            )
            result = await db.execute(query)
            habit = result.scalar_one_or_none()
            
            if not habit:
                return {'name': f'Habit {habit_id}', 'was_active': False}
            
            # For simplicity, assume habit was active if it exists
            # In a more complex system, you might track habit activation dates
            return {
                'name': habit.name,
                'was_active': habit.is_active
            }
            
        except Exception as e:
            logger.warning(f"Could not get habit details for habit {habit_id}: {str(e)}")
            return {'name': f'Habit {habit_id}', 'was_active': False}

# Global instance
calendar_crud = CalendarCRUD() 