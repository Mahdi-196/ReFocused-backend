"""
Daily App Interaction Streak Service

Tracks user engagement streaks based on meaningful daily interactions.
Unlike login streaks, this counts ANY meaningful app interaction per day.
"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
import logging
from enum import Enum

from app.db.models import User, UserDailyStreak
from app.services.time_service import TimeService

logger = logging.getLogger(__name__)

class InteractionType(Enum):
    """Types of meaningful app interactions that count toward daily streak"""
    HABIT_COMPLETION = "habit_completion"
    GOAL_PROGRESS = "goal_progress"
    MOOD_ENTRY = "mood_entry"
    JOURNAL_ENTRY = "journal_entry"
    STUDY_SESSION = "study_session"
    POMODORO_SESSION = "pomodoro_session"
    MEDITATION_SESSION = "meditation_session"
    GOAL_CREATION = "goal_creation"
    HABIT_CREATION = "habit_creation"
    CALENDAR_ENTRY = "calendar_entry"
    GRATITUDE_ENTRY = "gratitude_entry"
    PROFILE_UPDATE = "profile_update"
    SETTINGS_CHANGE = "settings_change"

class DailyStreakService:
    """Service for managing daily app interaction streaks"""
    
    def __init__(self, time_service: TimeService):
        self.time_service = time_service
    
    async def record_interaction(
        self,
        db: AsyncSession,
        user: User,
        interaction_type: InteractionType,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Record a meaningful app interaction and update streak if needed.
        
        Args:
            db: Database session
            user: User object
            interaction_type: Type of interaction
            metadata: Optional metadata about the interaction
            
        Returns:
            Dictionary with streak information and whether it was updated
        """
        try:
            # Get current date in user's timezone
            current_date = self.time_service.get_user_current_date(user)
            current_datetime = self.time_service.get_current_time_for_user(user)
            
            # Get or create today's streak record
            daily_record = await self._get_or_create_daily_record(
                db, user.id, current_date, user.timezone
            )
            
            # Update daily interaction tracking
            streak_info = await self._update_daily_interaction(
                db, user, daily_record, interaction_type, current_datetime, metadata
            )
            
            # Check if we need to update user's streak
            if daily_record.interaction_count == 1:  # First interaction of the day
                streak_info.update(await self._update_user_streak(db, user, current_date))
            
            await db.commit()
            
            logger.info(f"Recorded {interaction_type.value} for user {user.id}, current streak: {user.current_streak}")
            
            return streak_info
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error recording interaction for user {user.id}: {str(e)}")
            raise
    
    async def get_streak_status(self, db: AsyncSession, user: User) -> Dict[str, Any]:
        """Get current streak status for a user"""
        current_date = self.time_service.get_user_current_date(user)
        
        # Check if streak needs updating (user might have missed days)
        await self._validate_and_update_streak(db, user, current_date)
        
        # Get today's interactions
        today_record = await self._get_daily_record(db, user.id, current_date)
        
        # Get recent streak history (last 7 days)
        recent_history = await self._get_recent_streak_history(db, user.id, current_date, 7)
        
        return {
            "current_streak": user.current_streak,
            "longest_streak": user.longest_streak,
            "today_interactions": today_record.interaction_count if today_record else 0,
            "today_interaction_types": today_record.interaction_types if today_record else [],
            "last_interaction_date": user.last_interaction_date.isoformat() if user.last_interaction_date else None,
            "streak_at_risk": self._is_streak_at_risk(user, current_date),
            "recent_history": recent_history
        }
    
    async def get_streak_leaderboard(
        self, 
        db: AsyncSession, 
        limit: int = 10,
        streak_type: str = "current"
    ) -> List[Dict[str, Any]]:
        """Get streak leaderboard (current or longest streaks)"""
        if streak_type == "longest":
            order_field = User.longest_streak
        else:
            order_field = User.current_streak
            
        result = await db.execute(
            select(User.id, User.name, User.current_streak, User.longest_streak)
            .where(User.is_active == True)
            .order_by(order_field.desc())
            .limit(limit)
        )
        
        return [
            {
                "user_id": row[0],
                "name": row[1] or "Anonymous",
                "current_streak": row[2],
                "longest_streak": row[3]
            }
            for row in result.fetchall()
        ]
    
    # Private helper methods
    
    async def _get_or_create_daily_record(
        self, 
        db: AsyncSession, 
        user_id: int, 
        date: date, 
        timezone: str
    ) -> UserDailyStreak:
        """Get or create daily streak record for a specific date"""
        record = await self._get_daily_record(db, user_id, date)
        
        if not record:
            record = UserDailyStreak(
                user_id=user_id,
                date=date,
                interaction_count=0,
                interaction_types=[],
                timezone=timezone
            )
            db.add(record)
            await db.flush()
        
        return record
    
    async def _get_daily_record(
        self, 
        db: AsyncSession, 
        user_id: int, 
        date: date
    ) -> Optional[UserDailyStreak]:
        """Get daily streak record for a specific date"""
        result = await db.execute(
            select(UserDailyStreak).where(
                and_(
                    UserDailyStreak.user_id == user_id,
                    UserDailyStreak.date == date
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def _update_daily_interaction(
        self,
        db: AsyncSession,
        user: User,
        daily_record: UserDailyStreak,
        interaction_type: InteractionType,
        current_datetime: datetime,
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Update daily interaction record"""
        # Increment interaction count
        daily_record.interaction_count += 1
        
        # Track interaction types (avoid duplicates)
        if interaction_type.value not in daily_record.interaction_types:
            daily_record.interaction_types = daily_record.interaction_types + [interaction_type.value]
        
        # Update timestamps
        if not daily_record.first_interaction:
            daily_record.first_interaction = current_datetime
        daily_record.last_interaction = current_datetime
        
        return {
            "interaction_recorded": True,
            "daily_interaction_count": daily_record.interaction_count,
            "interaction_type": interaction_type.value,
            "first_today": daily_record.interaction_count == 1
        }
    
    async def _update_user_streak(
        self, 
        db: AsyncSession, 
        user: User, 
        current_date: date
    ) -> Dict[str, Any]:
        """Update user's streak based on current date"""
        streak_updated = False
        streak_continued = False
        new_record = False
        
        if not user.last_interaction_date:
            # First ever interaction
            user.current_streak = 1
            user.longest_streak = 1
            streak_updated = True
            new_record = True
        else:
            days_since_last = (current_date - user.last_interaction_date).days
            
            if days_since_last == 0:
                # Same day - no streak change needed
                pass
            elif days_since_last == 1:
                # Consecutive day - extend streak
                user.current_streak += 1
                if user.current_streak > user.longest_streak:
                    user.longest_streak = user.current_streak
                    new_record = True
                streak_updated = True
                streak_continued = True
            else:
                # Gap in days - reset streak
                user.current_streak = 1
                streak_updated = True
        
        # Update last interaction date and timestamp
        user.last_interaction_date = current_date
        user.streak_updated_at = datetime.utcnow()
        
        return {
            "streak_updated": streak_updated,
            "streak_continued": streak_continued,
            "new_record": new_record,
            "current_streak": user.current_streak,
            "longest_streak": user.longest_streak
        }
    
    async def _validate_and_update_streak(
        self, 
        db: AsyncSession, 
        user: User, 
        current_date: date
    ) -> None:
        """Validate and update streak if user has missed days"""
        if not user.last_interaction_date:
            return
        
        days_since_last = (current_date - user.last_interaction_date).days
        
        # If more than 1 day gap and user still has a streak, reset it
        if days_since_last > 1 and user.current_streak > 0:
            user.current_streak = 0
            user.streak_updated_at = datetime.utcnow()
            await db.commit()
            logger.info(f"Reset streak for user {user.id} due to {days_since_last} day gap")
    
    def _is_streak_at_risk(self, user: User, current_date: date) -> bool:
        """Check if user's streak is at risk of being lost"""
        if not user.last_interaction_date or user.current_streak == 0:
            return False
        
        days_since_last = (current_date - user.last_interaction_date).days
        return days_since_last >= 1  # Streak at risk if haven't interacted today
    
    async def _get_recent_streak_history(
        self, 
        db: AsyncSession, 
        user_id: int, 
        current_date: date, 
        days: int
    ) -> List[Dict[str, Any]]:
        """Get recent streak history for visualization"""
        start_date = current_date - timedelta(days=days-1)
        
        result = await db.execute(
            select(UserDailyStreak).where(
                and_(
                    UserDailyStreak.user_id == user_id,
                    UserDailyStreak.date >= start_date,
                    UserDailyStreak.date <= current_date
                )
            ).order_by(UserDailyStreak.date.asc())
        )
        
        records = result.scalars().all()
        record_dict = {record.date: record for record in records}
        
        history = []
        for i in range(days):
            check_date = start_date + timedelta(days=i)
            record = record_dict.get(check_date)
            
            history.append({
                "date": check_date.isoformat(),
                "has_interaction": record is not None,
                "interaction_count": record.interaction_count if record else 0,
                "interaction_types": record.interaction_types if record else []
            })
        
        return history

# Create global instance
daily_streak_service = DailyStreakService(TimeService()) 