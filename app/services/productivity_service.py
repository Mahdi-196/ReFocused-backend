from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import logging

from app.db.models import (
    User, MonthlyProductivityScore, ActivityQualityLog, 
    MonthlyActivitySummary, MonthlyTargets, ScoreCalculationLog,
    Habit, HabitCompletion, JournalEntry, Goal2Week, GoalLongTerm,
    UserStatistics, Gratitude, MoodEntry
)
from app.services.time_service import TimeService

logger = logging.getLogger(__name__)

class ProductivityScoreCalculator:
    """
    Calculates monthly productivity scores.
    """
    
    ALGORITHM_VERSION = "1.0.0"
    
    # Tier thresholds
    TIER_THRESHOLDS = {
        0: (0, 15),     # Basic engagement
        1: (15, 40),    # Consistent activity
        2: (40, 70),    # Quality activities
        3: (70, 85),    # Excellence
        4: (85, 100)    # Perfect score
    }
    
    # Perfect score requirements
    PERFECT_SCORE_REQUIREMENTS = {
        'min_habits': 3,
        'min_habit_completion_rate': 85.0,
        'min_pomodoro_hours': 15.0,
        'min_journal_entries': 10,
        'min_meditation_sessions': 4,
        'min_app_days': 25
    }
    
    # Activity weights (equal weighting for quality activities)
    ACTIVITY_WEIGHTS = {
        'pomodoro_session': 1.0,
        'meditation_session': 1.0,
        'breathing_exercise': 1.0,
        'journal_entry': 3.0,  # 1 journal = 3 gratitude entries
        'gratitude_entry': 1.0,
        'goal_completion': 5.0,  # 1 goal = 5 habit completions
        'habit_completion': 1.0
    }
    
    def __init__(self, db: AsyncSession, time_service: TimeService):
        self.db = db
        self.time_service = time_service
    
    async def calculate_monthly_score(
        self, 
        user_id: int, 
        year: int, 
        month: int,
        force_recalculate: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate monthly productivity score for a user.
        """
        start_time = datetime.utcnow()
        
        try:
            if not force_recalculate:
                existing_score = await self._get_existing_score(user_id, year, month)
                if existing_score:
                    return self._format_score_response(existing_score)
            
            targets = await self._get_user_targets(user_id)
            activity_data = await self._collect_monthly_activity_data(user_id, year, month)
            
            score_breakdown = await self._calculate_score_components(
                activity_data, targets, year, month
            )
            
            final_score = self._calculate_final_score(score_breakdown)
            tier = self._determine_tier(final_score)
            
            score_record = await self._save_monthly_score(
                user_id, year, month, final_score, tier, score_breakdown
            )
            
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await self._log_calculation(
                user_id, year, month, activity_data, 
                score_breakdown, final_score, execution_time
            )
            
            return self._format_score_response(score_record)
            
        except Exception as e:
            logger.error(f"Error calculating monthly score for user {user_id}: {str(e)}")
            await self._log_calculation_error(user_id, year, month, str(e))
            raise
    
    async def _collect_monthly_activity_data(
        self, user_id: int, year: int, month: int
    ) -> Dict[str, Any]:
        """Collect all activity data for the specified month."""
        
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        habits_query = select(Habit).where(
            and_(Habit.user_id == user_id, Habit.is_active == True)
        ).options(selectinload(Habit.completions))
        
        habits_result = await self.db.execute(habits_query)
        habits = habits_result.scalars().all()
        
        habit_completions = []
        for habit in habits:
            month_completions = [
                completion for completion in habit.completions
                if month_start <= completion.date <= month_end
            ]
            habit_completions.extend(month_completions)
        
        journal_query = select(JournalEntry).join(JournalEntry.collection).where(
            and_(
                JournalEntry.collection.has(user_id=user_id),
                func.date(JournalEntry.created_at) >= month_start,
                func.date(JournalEntry.created_at) <= month_end
            )
        )
        journal_result = await self.db.execute(journal_query)
        journal_entries = journal_result.scalars().all()
        
        gratitude_query = select(Gratitude).where(
            and_(
                Gratitude.user_id == user_id,
                Gratitude.date >= month_start,
                Gratitude.date <= month_end
            )
        )
        gratitude_result = await self.db.execute(gratitude_query)
        gratitude_entries = gratitude_result.scalars().all()
        
        goals_2week_query = select(Goal2Week).where(
            and_(
                Goal2Week.user_id == user_id,
                Goal2Week.is_completed == True,
                func.date(Goal2Week.completed_at) >= month_start,
                func.date(Goal2Week.completed_at) <= month_end
            )
        )
        goals_2week_result = await self.db.execute(goals_2week_query)
        completed_2week_goals = goals_2week_result.scalars().all()
        
        goals_longterm_query = select(GoalLongTerm).where(
            and_(
                GoalLongTerm.user_id == user_id,
                GoalLongTerm.is_completed == True,
                func.date(GoalLongTerm.completed_at) >= month_start,
                func.date(GoalLongTerm.completed_at) <= month_end
            )
        )
        goals_longterm_result = await self.db.execute(goals_longterm_query)
        completed_longterm_goals = goals_longterm_result.scalars().all()
        
        stats_query = select(UserStatistics).where(
            and_(
                UserStatistics.user_id == user_id,
                UserStatistics.date >= month_start,
                UserStatistics.date <= month_end
            )
        )
        stats_result = await self.db.execute(stats_query)
        user_stats = stats_result.scalars().all()
        
        activity_logs_query = select(ActivityQualityLog).where(
            and_(
                ActivityQualityLog.user_id == user_id,
                ActivityQualityLog.date >= month_start,
                ActivityQualityLog.date <= month_end
            )
        )
        activity_logs_result = await self.db.execute(activity_logs_query)
        activity_logs = activity_logs_result.scalars().all()
        
        app_days = set()
        for completion in habit_completions:
            app_days.add(completion.date)
        for entry in journal_entries:
            app_days.add(entry.created_at.date())
        for entry in gratitude_entries:
            app_days.add(entry.date)
        for stat in user_stats:
            if stat.focus_time_minutes > 0 or stat.completed_sessions > 0:
                app_days.add(stat.date)
        
        return {
            'habits': habits,
            'habit_completions': habit_completions,
            'journal_entries': journal_entries,
            'gratitude_entries': gratitude_entries,
            'completed_2week_goals': completed_2week_goals,
            'completed_longterm_goals': completed_longterm_goals,
            'user_stats': user_stats,
            'activity_logs': activity_logs,
            'app_days': len(app_days),
            'month_start': month_start,
            'month_end': month_end
        }
    
    async def _calculate_score_components(
        self, activity_data: Dict[str, Any], targets: Dict[str, Any], year: int, month: int
    ) -> Dict[str, Any]:
        """Calculate individual score components."""
        
        habits_score = self._calculate_habits_score(activity_data, targets)
        focus_score = self._calculate_focus_score(activity_data, targets)
        wellness_score = self._calculate_wellness_score(activity_data, targets)
        goals_score = self._calculate_goals_score(activity_data, targets)
        journal_score = self._calculate_journal_score(activity_data, targets)
        consistency_multiplier = self._calculate_consistency_multiplier(
            activity_data, targets
        )
        
        return {
            'habits_score': habits_score,
            'focus_score': focus_score,
            'wellness_score': wellness_score,
            'goals_score': goals_score,
            'journal_score': journal_score,
            'consistency_multiplier': consistency_multiplier,
            'app_days': activity_data['app_days'],
            'targets': targets
        }
    
    def _calculate_habits_score(self, activity_data: Dict[str, Any], targets: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate habits-based score component."""
        habits = activity_data['habits']
        completions = activity_data['habit_completions']
        
        if not habits:
            return {'score': 0, 'completion_rate': 0, 'active_habits': 0}
        
        # Calculate completion rate
        total_possible = len(habits) * self._days_in_month(
            activity_data['month_start'].year, activity_data['month_start'].month
        )
        total_completed = len(completions)
        completion_rate = (total_completed / total_possible * 100) if total_possible > 0 else 0
        
        # Score based on completion rate vs target
        target_rate = targets.get('target_habit_completion_rate', 80.0)
        if completion_rate >= target_rate:
            score = min(30, (completion_rate / target_rate) * 30)
        else:
            score = (completion_rate / target_rate) * 20
        
        return {
            'score': round(score, 2),
            'completion_rate': round(completion_rate, 2),
            'active_habits': len(habits),
            'total_completions': total_completed
        }
    
    def _calculate_focus_score(self, activity_data: Dict[str, Any], targets: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate focus/pomodoro score component."""
        user_stats = activity_data['user_stats']
        
        # Calculate total focus time
        total_focus_minutes = sum(stat.focus_time_minutes for stat in user_stats)
        total_focus_hours = total_focus_minutes / 60
        
        # Score based on focus hours vs target
        target_hours = targets.get('target_pomodoro_hours', 12.0)
        if total_focus_hours >= target_hours:
            score = min(25, (total_focus_hours / target_hours) * 25)
        else:
            score = (total_focus_hours / target_hours) * 20
        
        return {
            'score': round(score, 2),
            'total_hours': round(total_focus_hours, 2),
            'total_sessions': sum(stat.completed_sessions for stat in user_stats)
        }
    
    def _calculate_wellness_score(self, activity_data: Dict[str, Any], targets: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate wellness/meditation score component."""
        activity_logs = activity_data['activity_logs']
        
        # Count meditation and breathing sessions
        meditation_sessions = len([
            log for log in activity_logs 
            if log.activity_type in ['meditation', 'breathing']
        ])
        
        # Score based on meditation sessions vs target
        target_sessions = targets.get('target_meditation_sessions', 4)
        if meditation_sessions >= target_sessions:
            score = min(20, (meditation_sessions / target_sessions) * 20)
        else:
            score = (meditation_sessions / target_sessions) * 15
        
        return {
            'score': round(score, 2),
            'meditation_sessions': meditation_sessions
        }
    
    def _calculate_goals_score(self, activity_data: Dict[str, Any], targets: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate goals completion score component."""
        completed_2week = activity_data['completed_2week_goals']
        completed_longterm = activity_data['completed_longterm_goals']
        
        total_completed = len(completed_2week) + len(completed_longterm)
        
        # Higher weight for goal completion (impact-based scoring)
        if total_completed >= 3:
            score = 15
        elif total_completed >= 2:
            score = 12
        elif total_completed >= 1:
            score = 8
        else:
            score = 0
        
        return {
            'score': score,
            'total_completed': total_completed,
            'short_term_completed': len(completed_2week),
            'long_term_completed': len(completed_longterm)
        }
    
    def _calculate_journal_score(self, activity_data: Dict[str, Any], targets: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate journal/reflection score component."""
        journal_entries = activity_data['journal_entries']
        gratitude_entries = activity_data['gratitude_entries']
        
        # Weight journal entries higher (depth over quantity)
        journal_weighted = len(journal_entries) * 3
        gratitude_weighted = len(gratitude_entries)
        total_weighted = journal_weighted + gratitude_weighted
        
        # Score based on weighted entries vs target
        target_entries = targets.get('target_journal_entries', 8)
        weighted_target = target_entries * 3  # Assuming mostly journal entries
        
        if total_weighted >= weighted_target:
            score = min(20, (total_weighted / weighted_target) * 20)
        else:
            score = (total_weighted / weighted_target) * 15
        
        return {
            'score': round(score, 2),
            'journal_entries': len(journal_entries),
            'gratitude_entries': len(gratitude_entries),
            'weighted_total': total_weighted
        }
    
    def _calculate_consistency_multiplier(self, activity_data: Dict[str, Any], targets: Dict[str, Any]) -> float:
        """Calculate consistency multiplier based on app engagement."""
        app_days = activity_data['app_days']
        target_days = targets.get('target_app_days', 20)
        
        if app_days >= target_days:
            return 1.2  # 20% bonus for consistency
        elif app_days >= target_days * 0.8:
            return 1.1  # 10% bonus for good consistency
        elif app_days >= target_days * 0.6:
            return 1.0  # No penalty
        else:
            return 0.9  # 10% penalty for poor consistency
    
    def _calculate_final_score(self, breakdown: Dict[str, Any]) -> float:
        """Calculate final weighted score."""
        base_score = (
            breakdown['habits_score']['score'] +
            breakdown['focus_score']['score'] +
            breakdown['wellness_score']['score'] +
            breakdown['goals_score']['score'] +
            breakdown['journal_score']['score']
        )
        
        # Apply consistency multiplier
        final_score = base_score * breakdown['consistency_multiplier']
        
        # Ensure score is within bounds
        return min(100.0, max(0.0, final_score))
    
    def _determine_tier(self, score: float) -> int:
        """Determine tier based on score."""
        for tier, (min_score, max_score) in self.TIER_THRESHOLDS.items():
            if min_score <= score < max_score:
                return tier
        return 4 if score >= 85 else 0
    
    def _days_in_month(self, year: int, month: int) -> int:
        """Get number of days in a month."""
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        return (next_month - date(year, month, 1)).days
    
    async def _get_user_targets(self, user_id: int) -> Dict[str, Any]:
        """Get user's monthly targets or defaults."""
        query = select(MonthlyTargets).where(MonthlyTargets.user_id == user_id)
        result = await self.db.execute(query)
        targets = result.scalar_one_or_none()
        
        if targets:
            return {
                'target_app_days': targets.target_app_days,
                'target_pomodoro_hours': float(targets.target_pomodoro_hours),
                'target_meditation_sessions': targets.target_meditation_sessions,
                'target_journal_entries': targets.target_journal_entries,
                'target_habit_count': targets.target_habit_count,
                'target_habit_completion_rate': float(targets.target_habit_completion_rate)
            }
        else:
            # Return defaults
            return {
                'target_app_days': 20,
                'target_pomodoro_hours': 12.0,
                'target_meditation_sessions': 4,
                'target_journal_entries': 8,
                'target_habit_count': 3,
                'target_habit_completion_rate': 80.0
            }
    
    async def _get_existing_score(self, user_id: int, year: int, month: int) -> Optional[MonthlyProductivityScore]:
        """Get existing monthly score if it exists."""
        query = select(MonthlyProductivityScore).where(
            and_(
                MonthlyProductivityScore.user_id == user_id,
                MonthlyProductivityScore.year == year,
                MonthlyProductivityScore.month == month
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _save_monthly_score(
        self, user_id: int, year: int, month: int, 
        score: float, tier: int, breakdown: Dict[str, Any]
    ) -> MonthlyProductivityScore:
        """Save monthly score to database."""
        existing = await self._get_existing_score(user_id, year, month)
        
        if existing:
            # Update existing record
            existing.score = Decimal(str(score))
            existing.tier = tier
            existing.goals_points = Decimal(str(breakdown['goals_score']['score']))
            existing.habits_points = Decimal(str(breakdown['habits_score']['score']))
            existing.focus_points = Decimal(str(breakdown['focus_score']['score']))
            existing.wellness_points = Decimal(str(breakdown['wellness_score']['score']))
            existing.consistency_multiplier = Decimal(str(breakdown['consistency_multiplier']))
            existing.calculation_data = breakdown
            existing.updated_at = datetime.utcnow()
            record = existing
        else:
            # Create new record
            record = MonthlyProductivityScore(
                user_id=user_id,
                month=month,
                year=year,
                score=Decimal(str(score)),
                tier=tier,
                goals_points=Decimal(str(breakdown['goals_score']['score'])),
                habits_points=Decimal(str(breakdown['habits_score']['score'])),
                focus_points=Decimal(str(breakdown['focus_score']['score'])),
                wellness_points=Decimal(str(breakdown['wellness_score']['score'])),
                consistency_multiplier=Decimal(str(breakdown['consistency_multiplier'])),
                calculation_data=breakdown
            )
            self.db.add(record)
        
        await self.db.commit()
        await self.db.refresh(record)
        return record
    
    async def _log_calculation(
        self, user_id: int, year: int, month: int, 
        input_data: Dict[str, Any], score_breakdown: Dict[str, Any],
        final_score: float, execution_time: int
    ) -> None:
        """Log calculation for audit trail."""
        log_entry = ScoreCalculationLog(
            user_id=user_id,
            month=month,
            year=year,
            algorithm_version=self.ALGORITHM_VERSION,
            input_data=input_data,
            score_breakdown=score_breakdown,
            final_score=Decimal(str(final_score)),
            execution_time_ms=execution_time
        )
        self.db.add(log_entry)
        await self.db.commit()
    
    async def _log_calculation_error(
        self, user_id: int, year: int, month: int, error: str
    ) -> None:
        """Log calculation error."""
        log_entry = ScoreCalculationLog(
            user_id=user_id,
            month=month,
            year=year,
            algorithm_version=self.ALGORITHM_VERSION,
            input_data={},
            score_breakdown={},
            final_score=Decimal('0'),
            errors={'error': error}
        )
        self.db.add(log_entry)
        await self.db.commit()
    
    def _format_score_response(self, score_record: MonthlyProductivityScore) -> Dict[str, Any]:
        """Format score record for API response."""
        return {
            'user_id': score_record.user_id,
            'year': score_record.year,
            'month': score_record.month,
            'score': float(score_record.score),
            'tier': score_record.tier,
            'breakdown': {
                'goals_points': float(score_record.goals_points),
                'habits_points': float(score_record.habits_points),
                'focus_points': float(score_record.focus_points),
                'wellness_points': float(score_record.wellness_points),
                'consistency_multiplier': float(score_record.consistency_multiplier)
            },
            'calculation_data': score_record.calculation_data,
            'created_at': score_record.created_at.isoformat(),
            'updated_at': score_record.updated_at.isoformat()
        }