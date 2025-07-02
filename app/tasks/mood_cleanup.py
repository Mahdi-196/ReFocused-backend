"""
Background tasks for mood entry cleanup.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from app.db.database import async_session
from app.crud.mood import MoodCRUD
from app.services.time_service import TimeService

logger = logging.getLogger(__name__)

class MoodCleanupTask:
    """Background task to clean up old mood entries."""
    
    @staticmethod
    async def cleanup_previous_day_entries(target_date: Optional[date] = None) -> int:
        """
        Clean up mood entries for all users, keeping only the most recent entry per day
        for dates before the target date (defaults to today).
        
        This should be run daily at midnight to clean up entries from the previous day.
        
        Returns the total number of entries deleted.
        """
        if target_date is None:
            target_date = date.today()
        
        logger.info(f"Starting mood cleanup for entries before {target_date}")
        
        try:
            async with async_session() as db:
                deleted_count = await MoodCRUD.cleanup_all_users_old_entries(db, target_date)
                
            logger.info(f"Mood cleanup completed. Deleted {deleted_count} old entries.")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during mood cleanup: {str(e)}")
            raise
    
    @staticmethod
    async def cleanup_user_entries(user_id: int, cutoff_date: Optional[date] = None) -> int:
        """
        Clean up mood entries for a specific user, keeping only the most recent entry per day
        for dates before the cutoff date (defaults to today).
        
        Returns the number of entries deleted for this user.
        """
        if cutoff_date is None:
            cutoff_date = date.today()
        
        logger.info(f"Starting mood cleanup for user {user_id} before {cutoff_date}")
        
        try:
            async with async_session() as db:
                deleted_count = await MoodCRUD.cleanup_old_mood_entries(db, user_id, cutoff_date)
                
            logger.info(f"Mood cleanup for user {user_id} completed. Deleted {deleted_count} entries.")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during mood cleanup for user {user_id}: {str(e)}")
            raise

class MoodCleanupScheduler:
    """Scheduler for mood cleanup tasks."""
    
    @staticmethod
    async def schedule_daily_cleanup():
        """
        Schedule daily cleanup at midnight.
        This is a simple implementation - in production you might want to use 
        a proper task queue like Celery or APScheduler.
        """
        while True:
            try:
                # Calculate time until next midnight
                now = datetime.now()
                tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                sleep_seconds = (tomorrow - now).total_seconds()
                
                logger.info(f"Scheduling next mood cleanup in {sleep_seconds} seconds at {tomorrow}")
                
                # Sleep until midnight
                await asyncio.sleep(sleep_seconds)
                
                # Run cleanup
                await MoodCleanupTask.cleanup_previous_day_entries()
                
            except Exception as e:
                logger.error(f"Error in mood cleanup scheduler: {str(e)}")
                # Sleep for an hour before retrying
                await asyncio.sleep(3600)

# Manual cleanup functions for testing/admin use
async def run_cleanup_for_date(target_date: date) -> int:
    """Manually run cleanup for a specific date."""
    return await MoodCleanupTask.cleanup_previous_day_entries(target_date)

async def run_cleanup_for_user(user_id: int, cutoff_date: Optional[date] = None) -> int:
    """Manually run cleanup for a specific user."""
    return await MoodCleanupTask.cleanup_user_entries(user_id, cutoff_date) 