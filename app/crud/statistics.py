from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta, datetime, timezone
from app.db.models import UserStatistics
from typing import List, Optional
import logging

class StatisticsCRUD:
    @staticmethod
    async def get_or_create_today(db: AsyncSession, user_id: int) -> UserStatistics:
        """Get today's statistics record for a user or create it if it doesn't exist."""
        from datetime import datetime, timezone
        
        # Debug multiple date calculations (keep for monitoring)
        local_today = date.today()
        utc_today = datetime.now(timezone.utc).date()
        naive_today = datetime.now().date()
        
        print(f"🔍 DEBUG: Local today: {local_today}")
        print(f"🔍 DEBUG: UTC today: {utc_today}")
        print(f"🔍 DEBUG: Naive today: {naive_today}")
        
        # USER-CENTRIC FIX: Use local date to match user's calendar expectations
        today = local_today  # Use local date instead of UTC
        print(f"🔍 DEBUG: Using LOCAL date for database: {today}")
        
        # Try to get today's record
        result = await db.execute(
            select(UserStatistics).where(
                and_(
                    UserStatistics.user_id == user_id,
                    UserStatistics.date == today
                )
            )
        )
        stats = result.scalars().first()
        
        # Create if not exists
        if not stats:
            print(f"🔍 DEBUG: Creating NEW record for user_id={user_id}, date={today}")
            stats = UserStatistics(
                user_id=user_id,
                date=today,
                focus_time_minutes=0,
                completed_sessions=0,
                completed_tasks=0
            )
            db.add(stats)
            await db.flush()
        else:
            print(f"🔍 DEBUG: Found EXISTING record id={stats.id}, date={stats.date}")
            
        return stats
    
    @staticmethod
    async def add_focus_time(db: AsyncSession, user_id: int, minutes: int) -> UserStatistics:
        """Add focus time to today's statistics."""
        logger = logging.getLogger(__name__)
        
        logger.info(f"🔍 CRUD: Adding {minutes} minutes for user_id={user_id}")
        stats = await StatisticsCRUD.get_or_create_today(db, user_id)
        logger.info(f"🔍 CRUD: Before update - focus_time_minutes={stats.focus_time_minutes}")
        
        stats.focus_time_minutes += minutes
        logger.info(f"🔍 CRUD: After update - focus_time_minutes={stats.focus_time_minutes}")
        
        try:
            await db.commit()
            logger.info(f"🔍 CRUD: Committed to database for user_id={user_id}, date={stats.date}")
        except Exception as e:
            logger.error(f"🔍 CRUD: COMMIT FAILED: {e}")
            raise
        
        return stats
    
    @staticmethod
    async def add_sessions(db: AsyncSession, user_id: int, increment: int) -> UserStatistics:
        """Add completed sessions to today's statistics."""
        stats = await StatisticsCRUD.get_or_create_today(db, user_id)
        stats.completed_sessions += increment
        await db.commit()
        return stats
    
    @staticmethod
    async def add_tasks(db: AsyncSession, user_id: int, increment: int) -> UserStatistics:
        """Add completed tasks to today's statistics."""
        stats = await StatisticsCRUD.get_or_create_today(db, user_id)
        stats.completed_tasks += increment
        await db.commit()
        return stats
    
    @staticmethod
    async def get_statistics(db: AsyncSession, user_id: int, filter_period: str = "D") -> dict:
        """
        Get statistics based on filter period:
        D: Daily (today only)
        W: Weekly (last 7 days)
        M: Monthly (last 30 days)
        """
        from datetime import datetime, timezone
        
        # Use local time to match user's calendar expectations
        today = date.today()  # Use local date instead of UTC
        
        if filter_period == "D":
            # Daily: Just today
            start_date = today
        elif filter_period == "W":
            # Weekly: Last 7 days
            start_date = today - timedelta(days=6)  # today + 6 previous days = 7 days
        elif filter_period == "M":
            # Monthly: Last 30 days
            start_date = today - timedelta(days=29)  # today + 29 previous days = 30 days
        else:
            # Default to daily if invalid filter
            start_date = today
        
        # Query statistics for the period
        result = await db.execute(
            select(
                func.sum(UserStatistics.focus_time_minutes).label("focus_time"),
                func.sum(UserStatistics.completed_sessions).label("sessions"),
                func.sum(UserStatistics.completed_tasks).label("tasks_done")
            ).where(
                and_(
                    UserStatistics.user_id == user_id,
                    UserStatistics.date >= start_date,
                    UserStatistics.date <= today
                )
            )
        )
        
        stats = result.first()
        
        # Handle case where there are no stats (all NULL/None)
        return {
            "focus_time": stats.focus_time or 0 if stats else 0,
            "sessions": stats.sessions or 0 if stats else 0,
            "tasks_done": stats.tasks_done or 0 if stats else 0
        }
    
    @staticmethod
    async def get_detailed_statistics(db: AsyncSession, user_id: int, filter_period: str = "D") -> dict:
        """
        Get detailed statistics with daily breakdown based on filter period.
        """
        summary = await StatisticsCRUD.get_statistics(db, user_id, filter_period)
        
        from datetime import datetime, timezone
        
        # Use local time to match user's calendar expectations
        today = date.today()  # Use local date instead of UTC
        
        if filter_period == "D":
            start_date = today
        elif filter_period == "W":
            start_date = today - timedelta(days=6)
        elif filter_period == "M":
            start_date = today - timedelta(days=29)
        else:
            start_date = today
        
        # Query daily statistics
        result = await db.execute(
            select(
                UserStatistics.date,
                UserStatistics.focus_time_minutes,
                UserStatistics.completed_sessions,
                UserStatistics.completed_tasks
            ).where(
                and_(
                    UserStatistics.user_id == user_id,
                    UserStatistics.date >= start_date,
                    UserStatistics.date <= today
                )
            ).order_by(UserStatistics.date)
        )
        
        daily_stats = result.all()
        
        daily = []
        for stat in daily_stats:
            daily.append({
                "date": stat.date,
                "focus_time": stat.focus_time_minutes,
                "sessions": stat.completed_sessions,
                "tasks_done": stat.completed_tasks
            })
        
        return {
            "summary": summary,
            "daily": daily
        }

    @staticmethod
    async def get_or_create_for_date(db: AsyncSession, user_id: int, target_date: str) -> UserStatistics:
        """Get statistics record for a specific date or create it if it doesn't exist."""
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Try to get the record for the specific date
        result = await db.execute(
            select(UserStatistics).where(
                and_(
                    UserStatistics.user_id == user_id,
                    UserStatistics.date == date_obj
                )
            )
        )
        stats = result.scalars().first()
        
        # Create if not exists
        if not stats:
            stats = UserStatistics(
                user_id=user_id,
                date=date_obj,
                focus_time_minutes=0,
                completed_sessions=0,
                completed_tasks=0
            )
            db.add(stats)
            await db.flush()
            
        return stats

    @staticmethod
    async def update_focus_time_for_date(db: AsyncSession, user_id: int, target_date: str, minutes: int) -> UserStatistics:
        """Update focus time for a specific date."""
        stats = await StatisticsCRUD.get_or_create_for_date(db, user_id, target_date)
        stats.focus_time_minutes = minutes
        await db.commit()
        return stats
    
    @staticmethod
    async def update_sessions_for_date(db: AsyncSession, user_id: int, target_date: str, sessions: int) -> UserStatistics:
        """Update completed sessions for a specific date."""
        stats = await StatisticsCRUD.get_or_create_for_date(db, user_id, target_date)
        stats.completed_sessions = sessions
        await db.commit()
        return stats
    
    @staticmethod
    async def update_tasks_for_date(db: AsyncSession, user_id: int, target_date: str, tasks: int) -> UserStatistics:
        """Update completed tasks for a specific date."""
        stats = await StatisticsCRUD.get_or_create_for_date(db, user_id, target_date)
        stats.completed_tasks = tasks
        await db.commit()
        return stats

    @staticmethod
    async def get_statistics_by_date_range(db: AsyncSession, user_id: int, start_date: date, end_date: date) -> dict:
        """
        Get statistics for a custom date range.
        """
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 CRUD: Querying stats for user_id={user_id}, date_range={start_date} to {end_date}")
        
        # Query statistics for the date range
        result = await db.execute(
            select(
                func.sum(UserStatistics.focus_time_minutes).label("focus_time"),
                func.sum(UserStatistics.completed_sessions).label("sessions"),
                func.sum(UserStatistics.completed_tasks).label("tasks_done")
            ).where(
                and_(
                    UserStatistics.user_id == user_id,
                    UserStatistics.date >= start_date,
                    UserStatistics.date <= end_date
                )
            )
        )
        
        stats = result.first()
        logger.info(f"🔍 CRUD: Query result: focus={stats.focus_time or 0}, sessions={stats.sessions or 0}, tasks={stats.tasks_done or 0}")
        
        # Handle case where there are no stats (all NULL/None)
        final_stats = {
            "focus_time": stats.focus_time or 0 if stats else 0,
            "sessions": stats.sessions or 0 if stats else 0,
            "tasks_done": stats.tasks_done or 0 if stats else 0
        }
        return final_stats

    @staticmethod
    async def get_detailed_statistics_by_date_range(db: AsyncSession, user_id: int, start_date: date, end_date: date) -> dict:
        """
        Get detailed statistics with daily breakdown for a custom date range.
        """
        summary = await StatisticsCRUD.get_statistics_by_date_range(db, user_id, start_date, end_date)
        
        # Query daily statistics
        result = await db.execute(
            select(
                UserStatistics.date,
                UserStatistics.focus_time_minutes,
                UserStatistics.completed_sessions,
                UserStatistics.completed_tasks
            ).where(
                and_(
                    UserStatistics.user_id == user_id,
                    UserStatistics.date >= start_date,
                    UserStatistics.date <= end_date
                )
            ).order_by(UserStatistics.date)
        )
        
        daily_stats = result.all()
        
        daily = []
        for stat in daily_stats:
            daily.append({
                "date": stat.date,
                "focus_time": stat.focus_time_minutes,
                "sessions": stat.completed_sessions,
                "tasks_done": stat.completed_tasks
            })
        
        return {
            "summary": summary,
            "daily": daily
        } 