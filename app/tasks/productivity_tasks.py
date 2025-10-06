from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from celery import Celery
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import sessionmaker
import logging

from app.core.config import settings
from app.db.database import sync_engine
from app.db.models import (
    User, MonthlyProductivityScore, ActivityQualityLog,
    MonthlyActivitySummary, MonthlyTargets, ScoreCalculationLog
)
from app.services.productivity_service import ProductivityScoreCalculator
from app.services.time_service import TimeService

logger = logging.getLogger(__name__)

# Create synchronous session for background tasks
SessionLocal = sessionmaker(bind=sync_engine)

def get_sync_db():
    """Get synchronous database session for background tasks."""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

class ProductivityTasks:
    """Background tasks for productivity score calculations."""
    
    @staticmethod
    def daily_score_update_task():
        """Update daily contributions to monthly scores."""
        try:
            db = get_sync_db()
            
            # Get current date
            current_date = datetime.utcnow().date()
            
            # Find users with activity in the last 24 hours
            yesterday = current_date - timedelta(days=1)
            
            # Get users who had activity yesterday
            activity_query = select(ActivityQualityLog.user_id).where(
                ActivityQualityLog.date >= yesterday
            ).distinct()
            
            result = db.execute(activity_query)
            user_ids = [row[0] for row in result.fetchall()]
            
            logger.info(f"Running daily score update for {len(user_ids)} users")
            
            # Update scores for each user
            for user_id in user_ids:
                try:
                    # Get user's current month
                    user_query = select(User).where(User.id == user_id)
                    user_result = db.execute(user_query)
                    user = user_result.scalar_one_or_none()
                    
                    if user:
                        # Update current month's score
                        ProductivityTasks._update_user_monthly_score(
                            db, user_id, current_date.year, current_date.month
                        )
                        
                except Exception as e:
                    logger.error(f"Error updating daily score for user {user_id}: {str(e)}")
                    continue
            
            db.commit()
            logger.info("Daily score update completed successfully")
            
        except Exception as e:
            logger.error(f"Error in daily score update task: {str(e)}")
            db.rollback()
            raise
        finally:
            db.close()
    
    @staticmethod
    def weekly_aggregation_task():
        """Compile weekly summaries and update aggregated data."""
        try:
            db = get_sync_db()
            
            # Get current date and week start
            current_date = datetime.utcnow().date()
            week_start = current_date - timedelta(days=current_date.weekday())
            
            logger.info(f"Running weekly aggregation for week starting {week_start}")
            
            # Get all users with activity in the past week
            activity_query = select(ActivityQualityLog.user_id).where(
                ActivityQualityLog.date >= week_start
            ).distinct()
            
            result = db.execute(activity_query)
            user_ids = [row[0] for row in result.fetchall()]
            
            # Process each user
            for user_id in user_ids:
                try:
                    ProductivityTasks._update_weekly_aggregation(
                        db, user_id, week_start, current_date
                    )
                except Exception as e:
                    logger.error(f"Error in weekly aggregation for user {user_id}: {str(e)}")
                    continue
            
            db.commit()
            logger.info("Weekly aggregation completed successfully")
            
        except Exception as e:
            logger.error(f"Error in weekly aggregation task: {str(e)}")
            db.rollback()
            raise
        finally:
            db.close()
    
    @staticmethod
    def monthly_finalization_task():
        """Finalize monthly scores and prepare for next month."""
        try:
            db = get_sync_db()
            
            # Get last month's date
            today = datetime.utcnow().date()
            if today.month == 1:
                last_month_year = today.year - 1
                last_month_month = 12
            else:
                last_month_year = today.year
                last_month_month = today.month - 1
            
            logger.info(f"Running monthly finalization for {last_month_year}-{last_month_month}")
            
            # Get all users who had activity last month
            month_start = date(last_month_year, last_month_month, 1)
            if last_month_month == 12:
                month_end = date(last_month_year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(last_month_year, last_month_month + 1, 1) - timedelta(days=1)
            
            activity_query = select(ActivityQualityLog.user_id).where(
                and_(
                    ActivityQualityLog.date >= month_start,
                    ActivityQualityLog.date <= month_end
                )
            ).distinct()
            
            result = db.execute(activity_query)
            user_ids = [row[0] for row in result.fetchall()]
            
            # Finalize scores for each user
            for user_id in user_ids:
                try:
                    ProductivityTasks._finalize_monthly_score(
                        db, user_id, last_month_year, last_month_month
                    )
                except Exception as e:
                    logger.error(f"Error finalizing monthly score for user {user_id}: {str(e)}")
                    continue
            
            db.commit()
            logger.info("Monthly finalization completed successfully")
            
        except Exception as e:
            logger.error(f"Error in monthly finalization task: {str(e)}")
            db.rollback()
            raise
        finally:
            db.close()
    
    @staticmethod
    def quality_assessment_task():
        """Real-time quality scoring for recent activities."""
        try:
            db = get_sync_db()
            
            # Get activities from the last hour that need quality assessment
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            
            query = select(ActivityQualityLog).where(
                and_(
                    ActivityQualityLog.timestamp >= cutoff_time,
                    ActivityQualityLog.quality_score == 0  # Not yet assessed
                )
            )
            
            result = db.execute(query)
            activities = result.scalars().all()
            
            logger.info(f"Running quality assessment for {len(activities)} activities")
            
            # Re-assess quality scores
            for activity in activities:
                try:
                    # This would normally be done by the ActivityLogger
                    # but we can recalculate here if needed
                    pass
                except Exception as e:
                    logger.error(f"Error assessing quality for activity {activity.id}: {str(e)}")
                    continue
            
            db.commit()
            logger.info("Quality assessment completed successfully")
            
        except Exception as e:
            logger.error(f"Error in quality assessment task: {str(e)}")
            db.rollback()
            raise
        finally:
            db.close()
    
    @staticmethod
    def data_cleanup_task():
        """Remove old logs and cache data."""
        try:
            db = get_sync_db()
            
            # Clean up old activity logs (older than 2 years)
            cleanup_date = datetime.utcnow().date() - timedelta(days=730)
            
            logger.info(f"Running data cleanup for data older than {cleanup_date}")
            
            # Delete old activity quality logs
            activity_delete_query = db.query(ActivityQualityLog).where(
                ActivityQualityLog.date < cleanup_date
            )
            deleted_activities = activity_delete_query.count()
            activity_delete_query.delete(synchronize_session=False)
            
            # Delete old calculation logs (older than 1 year)
            calc_cleanup_date = datetime.utcnow() - timedelta(days=365)
            calc_delete_query = db.query(ScoreCalculationLog).where(
                ScoreCalculationLog.calculation_timestamp < calc_cleanup_date
            )
            deleted_calculations = calc_delete_query.count()
            calc_delete_query.delete(synchronize_session=False)
            
            db.commit()
            logger.info(f"Data cleanup completed: {deleted_activities} activities, {deleted_calculations} calculations")
            
        except Exception as e:
            logger.error(f"Error in data cleanup task: {str(e)}")
            db.rollback()
            raise
        finally:
            db.close()
    
    @staticmethod
    def _update_user_monthly_score(db, user_id: int, year: int, month: int):
        """Update monthly score for a specific user."""
        # This would use the async ProductivityScoreCalculator
        # For now, we'll create a simplified version
        
        # Get or create monthly summary
        summary_query = select(MonthlyActivitySummary).where(
            and_(
                MonthlyActivitySummary.user_id == user_id,
                MonthlyActivitySummary.year == year,
                MonthlyActivitySummary.month == month
            )
        )
        
        result = db.execute(summary_query)
        summary = result.scalar_one_or_none()
        
        if not summary:
            summary = MonthlyActivitySummary(
                user_id=user_id,
                year=year,
                month=month
            )
            db.add(summary)
        
        # Update summary statistics
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        # Count activities by type
        activity_query = select(
            ActivityQualityLog.activity_type,
            func.count(ActivityQualityLog.id).label('count')
        ).where(
            and_(
                ActivityQualityLog.user_id == user_id,
                ActivityQualityLog.date >= month_start,
                ActivityQualityLog.date <= month_end
            )
        ).group_by(ActivityQualityLog.activity_type)
        
        result = db.execute(activity_query)
        activity_counts = {row[0]: row[1] for row in result.fetchall()}
        
        # Update summary fields
        summary.meditation_sessions = activity_counts.get('meditation', 0) + activity_counts.get('breathing', 0)
        summary.journal_entries = activity_counts.get('journal', 0)
        summary.goals_completed = activity_counts.get('goal', 0)
        summary.updated_at = datetime.utcnow()
        
        db.commit()
    
    @staticmethod
    def _update_weekly_aggregation(db, user_id: int, week_start: date, week_end: date):
        """Update weekly aggregation for a user."""
        # Get weekly activity statistics
        activity_query = select(
            ActivityQualityLog.activity_type,
            func.count(ActivityQualityLog.id).label('count'),
            func.avg(ActivityQualityLog.quality_score).label('avg_quality')
        ).where(
            and_(
                ActivityQualityLog.user_id == user_id,
                ActivityQualityLog.date >= week_start,
                ActivityQualityLog.date <= week_end
            )
        ).group_by(ActivityQualityLog.activity_type)
        
        result = db.execute(activity_query)
        weekly_stats = result.fetchall()
        
        # Log weekly statistics for monitoring
        logger.info(f"User {user_id} weekly stats: {weekly_stats}")
    
    @staticmethod
    def _finalize_monthly_score(db, user_id: int, year: int, month: int):
        """Finalize monthly score calculations."""
        # Force recalculation of monthly score
        # This would normally use the async calculator
        
        # Get existing score
        score_query = select(MonthlyProductivityScore).where(
            and_(
                MonthlyProductivityScore.user_id == user_id,
                MonthlyProductivityScore.year == year,
                MonthlyProductivityScore.month == month
            )
        )
        
        result = db.execute(score_query)
        score = result.scalar_one_or_none()
        
        if score:
            # Mark as finalized (could add a field for this)
            score.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Finalized monthly score for user {user_id}: {year}-{month}")

# Task registration functions for Celery
def register_productivity_tasks(celery_app: Celery):
    """Register productivity tasks with Celery."""
    
    @celery_app.task(bind=True, name='daily_score_update')
    def daily_score_update(self):
        """Daily score update task."""
        try:
            ProductivityTasks.daily_score_update_task()
            return {"status": "success", "message": "Daily score update completed"}
        except Exception as e:
            logger.error(f"Daily score update failed: {str(e)}")
            raise self.retry(exc=e, countdown=300, max_retries=3)
    
    @celery_app.task(bind=True, name='weekly_aggregation')
    def weekly_aggregation(self):
        """Weekly aggregation task."""
        try:
            ProductivityTasks.weekly_aggregation_task()
            return {"status": "success", "message": "Weekly aggregation completed"}
        except Exception as e:
            logger.error(f"Weekly aggregation failed: {str(e)}")
            raise self.retry(exc=e, countdown=600, max_retries=3)
    
    @celery_app.task(bind=True, name='monthly_finalization')
    def monthly_finalization(self):
        """Monthly finalization task."""
        try:
            ProductivityTasks.monthly_finalization_task()
            return {"status": "success", "message": "Monthly finalization completed"}
        except Exception as e:
            logger.error(f"Monthly finalization failed: {str(e)}")
            raise self.retry(exc=e, countdown=900, max_retries=2)
    
    @celery_app.task(bind=True, name='quality_assessment')
    def quality_assessment(self):
        """Quality assessment task."""
        try:
            ProductivityTasks.quality_assessment_task()
            return {"status": "success", "message": "Quality assessment completed"}
        except Exception as e:
            logger.error(f"Quality assessment failed: {str(e)}")
            raise self.retry(exc=e, countdown=60, max_retries=5)
    
    @celery_app.task(bind=True, name='data_cleanup')
    def data_cleanup(self):
        """Data cleanup task."""
        try:
            ProductivityTasks.data_cleanup_task()
            return {"status": "success", "message": "Data cleanup completed"}
        except Exception as e:
            logger.error(f"Data cleanup failed: {str(e)}")
            raise self.retry(exc=e, countdown=1800, max_retries=2)
    
    @celery_app.task(bind=True, name='recalculate_user_score')
    def recalculate_user_score(self, user_id: int, year: int, month: int):
        """Recalculate specific user's monthly score."""
        try:
            db = get_sync_db()
            ProductivityTasks._update_user_monthly_score(db, user_id, year, month)
            db.close()
            return {"status": "success", "message": f"Recalculated score for user {user_id}"}
        except Exception as e:
            logger.error(f"Score recalculation failed for user {user_id}: {str(e)}")
            raise self.retry(exc=e, countdown=120, max_retries=3)