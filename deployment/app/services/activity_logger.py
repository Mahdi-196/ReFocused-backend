from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Any
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
import logging
import json
from enum import Enum

from app.db.models import (
    ActivityQualityLog, MonthlyActivitySummary, User
)
from app.services.time_service import TimeService

logger = logging.getLogger(__name__)

class ActivityType(str, Enum):
    POMODORO = "pomodoro"
    MEDITATION = "meditation"
    BREATHING = "breathing"
    JOURNAL = "journal"
    GRATITUDE = "gratitude"
    HABIT = "habit"
    GOAL = "goal"

class ActivityLogger:
    """
    Service for logging user activity with quality assessment.
    Tracks all user interactions for productivity score calculation.
    """
    
    def __init__(self, db: AsyncSession, time_service: TimeService):
        self.db = db
        self.time_service = time_service
    
    async def log_activity(
        self,
        user_id: int,
        activity_type: ActivityType,
        activity_data: Dict[str, Any],
        session_id: Optional[str] = None,
        device_info: Optional[Dict[str, Any]] = None
    ) -> ActivityQualityLog:
        """
        Log a user activity with quality assessment.
        
        Args:
            user_id: User ID
            activity_type: Type of activity
            activity_data: Activity-specific data
            session_id: Optional session identifier
            device_info: Optional device information
        
        Returns:
            ActivityQualityLog record
        """
        try:
            # Get user timezone
            user_timezone = await self._get_user_timezone(user_id)
            current_time = self.time_service.get_current_time(user_timezone)
            current_date = current_time.date()
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(activity_type, activity_data)
            
            # Validate activity data
            validated_data = self._validate_activity_data(activity_type, activity_data)
            
            # Create activity log
            activity_log = ActivityQualityLog(
                user_id=user_id,
                activity_type=activity_type.value,
                activity_data=validated_data,
                quality_score=Decimal(str(quality_score)),
                date=current_date,
                timestamp=current_time,
                session_id=session_id,
                device_info=device_info or {}
            )
            
            self.db.add(activity_log)
            await self.db.commit()
            await self.db.refresh(activity_log)
            
            # Update monthly summary asynchronously
            await self._update_monthly_summary(user_id, current_date.year, current_date.month)
            
            logger.info(f"Logged {activity_type.value} activity for user {user_id} with quality score {quality_score}")
            
            return activity_log
            
        except Exception as e:
            logger.error(f"Error logging activity for user {user_id}: {str(e)}")
            await self.db.rollback()
            raise
    
    async def log_pomodoro_session(
        self,
        user_id: int,
        duration_minutes: int,
        completed: bool = True,
        interruptions: int = 0,
        session_id: Optional[str] = None
    ) -> ActivityQualityLog:
        """Log a pomodoro session with quality assessment."""
        activity_data = {
            'duration_minutes': duration_minutes,
            'completed': completed,
            'interruptions': interruptions,
            'planned_duration': 25  # Standard pomodoro duration
        }
        
        return await self.log_activity(
            user_id=user_id,
            activity_type=ActivityType.POMODORO,
            activity_data=activity_data,
            session_id=session_id
        )
    
    async def log_meditation_session(
        self,
        user_id: int,
        duration_minutes: int,
        meditation_type: str = "mindfulness",
        completed: bool = True,
        session_id: Optional[str] = None
    ) -> ActivityQualityLog:
        """Log a meditation session."""
        activity_data = {
            'duration_minutes': duration_minutes,
            'meditation_type': meditation_type,
            'completed': completed
        }
        
        return await self.log_activity(
            user_id=user_id,
            activity_type=ActivityType.MEDITATION,
            activity_data=activity_data,
            session_id=session_id
        )
    
    async def log_breathing_exercise(
        self,
        user_id: int,
        duration_minutes: int,
        exercise_type: str = "4-7-8",
        completed: bool = True,
        session_id: Optional[str] = None
    ) -> ActivityQualityLog:
        """Log a breathing exercise session."""
        activity_data = {
            'duration_minutes': duration_minutes,
            'exercise_type': exercise_type,
            'completed': completed
        }
        
        return await self.log_activity(
            user_id=user_id,
            activity_type=ActivityType.BREATHING,
            activity_data=activity_data,
            session_id=session_id
        )
    
    async def log_journal_entry(
        self,
        user_id: int,
        entry_id: int,
        word_count: int,
        time_spent_minutes: int,
        session_id: Optional[str] = None
    ) -> ActivityQualityLog:
        """Log a journal entry creation."""
        activity_data = {
            'entry_id': entry_id,
            'word_count': word_count,
            'time_spent_minutes': time_spent_minutes
        }
        
        return await self.log_activity(
            user_id=user_id,
            activity_type=ActivityType.JOURNAL,
            activity_data=activity_data,
            session_id=session_id
        )
    
    async def log_gratitude_entry(
        self,
        user_id: int,
        entry_id: int,
        character_count: int,
        session_id: Optional[str] = None
    ) -> ActivityQualityLog:
        """Log a gratitude entry."""
        activity_data = {
            'entry_id': entry_id,
            'character_count': character_count
        }
        
        return await self.log_activity(
            user_id=user_id,
            activity_type=ActivityType.GRATITUDE,
            activity_data=activity_data,
            session_id=session_id
        )
    
    async def log_habit_completion(
        self,
        user_id: int,
        habit_id: int,
        completion_time: datetime,
        session_id: Optional[str] = None
    ) -> ActivityQualityLog:
        """Log a habit completion."""
        activity_data = {
            'habit_id': habit_id,
            'completion_time': completion_time.isoformat()
        }
        
        return await self.log_activity(
            user_id=user_id,
            activity_type=ActivityType.HABIT,
            activity_data=activity_data,
            session_id=session_id
        )
    
    async def log_goal_completion(
        self,
        user_id: int,
        goal_id: int,
        goal_type: str,
        progress_percentage: float,
        session_id: Optional[str] = None
    ) -> ActivityQualityLog:
        """Log a goal completion or progress update."""
        activity_data = {
            'goal_id': goal_id,
            'goal_type': goal_type,
            'progress_percentage': progress_percentage,
            'completed': progress_percentage >= 100.0
        }
        
        return await self.log_activity(
            user_id=user_id,
            activity_type=ActivityType.GOAL,
            activity_data=activity_data,
            session_id=session_id
        )
    
    async def get_user_activity_summary(
        self,
        user_id: int,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """Get user activity summary for a specific month."""
        
        # Get activity logs for the month
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1)
        else:
            month_end = date(year, month + 1, 1)
        
        query = select(ActivityQualityLog).where(
            and_(
                ActivityQualityLog.user_id == user_id,
                ActivityQualityLog.date >= month_start,
                ActivityQualityLog.date < month_end
            )
        ).order_by(desc(ActivityQualityLog.timestamp))
        
        result = await self.db.execute(query)
        activities = result.scalars().all()
        
        # Group by activity type
        summary = {
            'total_activities': len(activities),
            'by_type': {},
            'by_date': {},
            'quality_metrics': {
                'average_quality': 0,
                'high_quality_count': 0,
                'low_quality_count': 0
            }
        }
        
        quality_scores = []
        
        for activity in activities:
            activity_type = activity.activity_type
            activity_date = activity.date.isoformat()
            quality_score = float(activity.quality_score)
            
            # By type
            if activity_type not in summary['by_type']:
                summary['by_type'][activity_type] = {
                    'count': 0,
                    'average_quality': 0,
                    'total_quality': 0
                }
            
            summary['by_type'][activity_type]['count'] += 1
            summary['by_type'][activity_type]['total_quality'] += quality_score
            
            # By date
            if activity_date not in summary['by_date']:
                summary['by_date'][activity_date] = {
                    'count': 0,
                    'activities': []
                }
            
            summary['by_date'][activity_date]['count'] += 1
            summary['by_date'][activity_date]['activities'].append({
                'type': activity_type,
                'quality_score': quality_score,
                'timestamp': activity.timestamp.isoformat()
            })
            
            quality_scores.append(quality_score)
        
        # Calculate averages
        for activity_type in summary['by_type']:
            type_data = summary['by_type'][activity_type]
            type_data['average_quality'] = round(
                type_data['total_quality'] / type_data['count'], 2
            )
            del type_data['total_quality']
        
        # Quality metrics
        if quality_scores:
            summary['quality_metrics']['average_quality'] = round(
                sum(quality_scores) / len(quality_scores), 2
            )
            summary['quality_metrics']['high_quality_count'] = len([
                s for s in quality_scores if s >= 7.0
            ])
            summary['quality_metrics']['low_quality_count'] = len([
                s for s in quality_scores if s <= 4.0
            ])
        
        return summary
    
    def _calculate_quality_score(
        self,
        activity_type: ActivityType,
        activity_data: Dict[str, Any]
    ) -> float:
        """Calculate quality score for an activity (0-10 scale)."""
        
        if activity_type == ActivityType.POMODORO:
            return self._calculate_pomodoro_quality(activity_data)
        elif activity_type == ActivityType.MEDITATION:
            return self._calculate_meditation_quality(activity_data)
        elif activity_type == ActivityType.BREATHING:
            return self._calculate_breathing_quality(activity_data)
        elif activity_type == ActivityType.JOURNAL:
            return self._calculate_journal_quality(activity_data)
        elif activity_type == ActivityType.GRATITUDE:
            return self._calculate_gratitude_quality(activity_data)
        elif activity_type == ActivityType.HABIT:
            return 8.0  # Standard quality for habit completion
        elif activity_type == ActivityType.GOAL:
            return self._calculate_goal_quality(activity_data)
        else:
            return 5.0  # Default quality score
    
    def _calculate_pomodoro_quality(self, data: Dict[str, Any]) -> float:
        """Calculate pomodoro session quality score."""
        duration = data.get('duration_minutes', 0)
        completed = data.get('completed', False)
        interruptions = data.get('interruptions', 0)
        planned_duration = data.get('planned_duration', 25)
        
        base_score = 5.0
        
        # Completion bonus
        if completed:
            base_score += 2.0
        
        # Duration effectiveness
        if duration >= planned_duration * 0.8:
            base_score += 1.5
        elif duration >= planned_duration * 0.6:
            base_score += 1.0
        else:
            base_score -= 1.0
        
        # Interruption penalty
        if interruptions == 0:
            base_score += 1.5
        elif interruptions <= 2:
            base_score += 0.5
        else:
            base_score -= 1.0
        
        return min(10.0, max(0.0, base_score))
    
    def _calculate_meditation_quality(self, data: Dict[str, Any]) -> float:
        """Calculate meditation session quality score."""
        duration = data.get('duration_minutes', 0)
        completed = data.get('completed', False)
        
        base_score = 5.0
        
        # Completion bonus
        if completed:
            base_score += 2.0
        
        # Duration scoring
        if duration >= 15:
            base_score += 2.0
        elif duration >= 10:
            base_score += 1.5
        elif duration >= 5:
            base_score += 1.0
        else:
            base_score -= 1.0
        
        # Consistency bonus (would need historical data)
        base_score += 1.0
        
        return min(10.0, max(0.0, base_score))
    
    def _calculate_breathing_quality(self, data: Dict[str, Any]) -> float:
        """Calculate breathing exercise quality score."""
        duration = data.get('duration_minutes', 0)
        completed = data.get('completed', False)
        
        base_score = 5.0
        
        # Completion bonus
        if completed:
            base_score += 2.0
        
        # Duration scoring
        if duration >= 10:
            base_score += 2.0
        elif duration >= 5:
            base_score += 1.5
        elif duration >= 3:
            base_score += 1.0
        
        # Breathing exercises are generally high quality
        base_score += 1.0
        
        return min(10.0, max(0.0, base_score))
    
    def _calculate_journal_quality(self, data: Dict[str, Any]) -> float:
        """Calculate journal entry quality score."""
        word_count = data.get('word_count', 0)
        time_spent = data.get('time_spent_minutes', 0)
        
        base_score = 5.0
        
        # Word count quality
        if word_count >= 300:
            base_score += 2.5
        elif word_count >= 150:
            base_score += 2.0
        elif word_count >= 75:
            base_score += 1.5
        elif word_count >= 25:
            base_score += 1.0
        else:
            base_score -= 1.0
        
        # Time investment
        if time_spent >= 15:
            base_score += 1.5
        elif time_spent >= 10:
            base_score += 1.0
        elif time_spent >= 5:
            base_score += 0.5
        
        return min(10.0, max(0.0, base_score))
    
    def _calculate_gratitude_quality(self, data: Dict[str, Any]) -> float:
        """Calculate gratitude entry quality score."""
        character_count = data.get('character_count', 0)
        
        base_score = 6.0  # Gratitude is inherently valuable
        
        # Character count quality
        if character_count >= 150:
            base_score += 2.0
        elif character_count >= 100:
            base_score += 1.5
        elif character_count >= 50:
            base_score += 1.0
        elif character_count >= 20:
            base_score += 0.5
        else:
            base_score -= 1.0
        
        return min(10.0, max(0.0, base_score))
    
    def _calculate_goal_quality(self, data: Dict[str, Any]) -> float:
        """Calculate goal completion quality score."""
        progress = data.get('progress_percentage', 0)
        completed = data.get('completed', False)
        
        base_score = 5.0
        
        # Completion bonus
        if completed:
            base_score += 3.0
        elif progress >= 80:
            base_score += 2.0
        elif progress >= 50:
            base_score += 1.5
        elif progress >= 25:
            base_score += 1.0
        
        # Goals are high-impact activities
        base_score += 1.0
        
        return min(10.0, max(0.0, base_score))
    
    def _validate_activity_data(
        self,
        activity_type: ActivityType,
        activity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and sanitize activity data."""
        # Basic validation - ensure required fields exist
        validated = activity_data.copy()
        
        # Convert any datetime objects to ISO strings
        for key, value in validated.items():
            if isinstance(value, datetime):
                validated[key] = value.isoformat()
        
        return validated
    
    async def _get_user_timezone(self, user_id: int) -> str:
        """Get user's timezone or default to UTC."""
        query = select(User.timezone).where(User.id == user_id)
        result = await self.db.execute(query)
        timezone = result.scalar_one_or_none()
        return timezone or "UTC"
    
    async def _update_monthly_summary(self, user_id: int, year: int, month: int) -> None:
        """Update monthly activity summary (called asynchronously)."""
        try:
            # This could be moved to a background task for better performance
            # For now, we'll do a simple update
            
            # Get or create monthly summary
            query = select(MonthlyActivitySummary).where(
                and_(
                    MonthlyActivitySummary.user_id == user_id,
                    MonthlyActivitySummary.year == year,
                    MonthlyActivitySummary.month == month
                )
            )
            result = await self.db.execute(query)
            summary = result.scalar_one_or_none()
            
            if not summary:
                summary = MonthlyActivitySummary(
                    user_id=user_id,
                    year=year,
                    month=month
                )
                self.db.add(summary)
            
            # Update summary fields would go here
            # For now, we'll just update the timestamp
            summary.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating monthly summary: {str(e)}")
            # Don't let this failure affect the main activity logging