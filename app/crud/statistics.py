from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from sqlalchemy.orm import Session
from datetime import date, timedelta, datetime
from app.db.models import UserStatistics
from typing import List, Optional

class StatisticsCRUD:
    @staticmethod
    async def get_or_create_today(db: AsyncSession, user_id: int) -> UserStatistics:
        """Get today's statistics record for a user or create it if it doesn't exist."""
        today = date.today()
        
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
            stats = UserStatistics(
                user_id=user_id,
                date=today,
                focus_time_seconds=0,
                completed_sessions=0,
                completed_tasks=0
            )
            db.add(stats)
            await db.flush()
            
        return stats
    
    @staticmethod
    async def add_focus_time(db: AsyncSession, user_id: int, seconds: int) -> UserStatistics:
        """Add focus time to today's statistics."""
        stats = await StatisticsCRUD.get_or_create_today(db, user_id)
        stats.focus_time_seconds += seconds
        await db.commit()
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
        today = date.today()
        
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
                func.sum(UserStatistics.focus_time_seconds).label("focus_time"),
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
        
        today = date.today()
        
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
                UserStatistics.focus_time_seconds,
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
                "focus_time": stat.focus_time_seconds,
                "sessions": stat.completed_sessions,
                "tasks_done": stat.completed_tasks
            })
        
        return {
            "summary": summary,
            "daily": daily
        } 