"""
Daily Streak API Endpoints

Provides endpoints for users to view their daily interaction streaks,
leaderboards, and streak history.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
import logging

from app.db.database import get_db
from app.core.auth import get_current_user
from app.db.models import User
from app.services.daily_streak_service import daily_streak_service, InteractionType

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/status")
async def get_streak_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's daily interaction streak status.
    
    Returns:
    - Current streak count
    - Longest streak ever achieved
    - Today's interaction count and types
    - Whether streak is at risk
    - Last 7 days of interaction history
    """
    try:
        streak_data = await daily_streak_service.get_streak_status(db, current_user)
        
        return {
            "success": True,
            **streak_data
        }
        
    except Exception as e:
        logger.error(f"Error getting streak status for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve streak status"
        )

@router.get("/leaderboard")
async def get_streak_leaderboard(
    streak_type: str = Query("current", regex="^(current|longest)$", description="Type of streak leaderboard"),
    limit: int = Query(10, ge=1, le=100, description="Number of users to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get streak leaderboard.
    
    Args:
    - streak_type: 'current' for current streaks, 'longest' for all-time longest
    - limit: Number of users to include (1-100)
    
    Returns:
    - Leaderboard with top users
    - Current user's rank and streak
    """
    try:
        # Get leaderboard
        leaderboard = await daily_streak_service.get_streak_leaderboard(
            db, limit=limit, streak_type=streak_type
        )
        
        # Find current user's rank
        user_rank = None
        user_streak = current_user.current_streak if streak_type == "current" else current_user.longest_streak
        
        for i, entry in enumerate(leaderboard):
            if entry["user_id"] == current_user.id:
                user_rank = i + 1
                break
        
        return {
            "success": True,
            "leaderboard": leaderboard,
            "user_rank": user_rank,
            "user_streak": user_streak
        }
        
    except Exception as e:
        logger.error(f"Error getting streak leaderboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve streak leaderboard"
        )

@router.get("/history")
async def get_streak_history(
    days: int = Query(30, ge=7, le=365, description="Number of days to retrieve"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed streak history for visualization.
    
    Args:
    - days: Number of days to retrieve (7-365)
    
    Returns:
    - Daily interaction history
    - Streak patterns and statistics
    """
    try:
        from app.services.time_service import TimeService
        time_service = TimeService()
        current_date = time_service.get_user_current_date(current_user)
        
        # Get detailed history
        history = await daily_streak_service._get_recent_streak_history(
            db, current_user.id, current_date, days
        )
        
        # Calculate statistics
        total_active_days = sum(1 for day in history if day["has_interaction"])
        total_interactions = sum(day["interaction_count"] for day in history)
        consistency_rate = (total_active_days / days) * 100
        
        # Find longest streak in period
        longest_streak_in_period = 0
        current_streak_in_period = 0
        
        for day in reversed(history):  # Start from most recent
            if day["has_interaction"]:
                current_streak_in_period += 1
                longest_streak_in_period = max(longest_streak_in_period, current_streak_in_period)
            else:
                current_streak_in_period = 0
        
        return {
            "success": True,
            "period_days": days,
            "start_date": history[0]["date"] if history else None,
            "end_date": history[-1]["date"] if history else None,
            "statistics": {
                "total_active_days": total_active_days,
                "total_interactions": total_interactions,
                "consistency_rate": round(consistency_rate, 1),
                "average_interactions_per_active_day": round(total_interactions / max(total_active_days, 1), 1),
                "longest_streak_in_period": longest_streak_in_period
            },
            "daily_history": history
        }
        
    except Exception as e:
        logger.error(f"Error getting streak history for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve streak history"
        )

@router.post("/manual-checkin")
async def manual_checkin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manual check-in endpoint for users who want to maintain their streak
    without performing other meaningful actions.
    
    This can be useful for days when users just want to "check in" 
    to maintain their daily interaction streak.
    """
    try:
        result = await daily_streak_service.record_interaction(
            db, 
            current_user, 
            InteractionType.PROFILE_UPDATE,  # Use a generic interaction type
            metadata={"manual_checkin": True, "source": "manual_checkin_endpoint"}
        )
        
        return {
            "success": True,
            "message": "Daily check-in recorded successfully",
            "current_streak": current_user.current_streak,
            "longest_streak": current_user.longest_streak,
            "interaction_details": result
        }
        
    except Exception as e:
        logger.error(f"Error recording manual check-in for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record check-in"
        )

@router.get("/interaction-types")
async def get_interaction_types():
    """
    Get list of interaction types that count toward daily streaks.
    
    Useful for frontend to show users what activities maintain their streak.
    """
    interaction_descriptions = {
        InteractionType.HABIT_COMPLETION: "Complete a habit",
        InteractionType.GOAL_PROGRESS: "Make progress on a goal",
        InteractionType.MOOD_ENTRY: "Log your mood",
        InteractionType.JOURNAL_ENTRY: "Write in your journal",
        InteractionType.STUDY_SESSION: "Study with flashcards",
        InteractionType.POMODORO_SESSION: "Complete a focus session",
        InteractionType.MEDITATION_SESSION: "Complete a meditation",
        InteractionType.GOAL_CREATION: "Create a new goal",
        InteractionType.HABIT_CREATION: "Create a new habit",
        InteractionType.CALENDAR_ENTRY: "Update your calendar",
        InteractionType.GRATITUDE_ENTRY: "Write a gratitude entry",
        InteractionType.PROFILE_UPDATE: "Update your profile",
        InteractionType.SETTINGS_CHANGE: "Modify your settings"
    }
    
    return {
        "success": True,
        "interaction_types": [
            {
                "type": interaction_type.value,
                "description": interaction_descriptions[interaction_type],
                "category": interaction_type.value.split("_")[0].title()
            }
            for interaction_type in InteractionType
        ]
    }

@router.get("/stats")
async def get_streak_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive streak statistics for the user.
    
    Returns aggregated statistics and insights about user engagement patterns.
    """
    try:
        from app.services.time_service import TimeService
        from sqlalchemy import select, func
        from app.db.models import UserDailyStreak
        
        time_service = TimeService()
        current_date = time_service.get_user_current_date(current_user)
        
        # Get all-time statistics
        result = await db.execute(
            select(
                func.count(UserDailyStreak.id).label("total_active_days"),
                func.sum(UserDailyStreak.interaction_count).label("total_interactions"),
                func.avg(UserDailyStreak.interaction_count).label("avg_interactions_per_day"),
                func.min(UserDailyStreak.date).label("first_active_date"),
                func.max(UserDailyStreak.date).label("last_active_date")
            ).where(UserDailyStreak.user_id == current_user.id)
        )
        
        stats = result.first()
        
        # Calculate days since first interaction
        days_since_start = 0
        if stats.first_active_date:
            days_since_start = (current_date - stats.first_active_date).days + 1
        
        # Calculate overall consistency
        overall_consistency = 0
        if days_since_start > 0:
            overall_consistency = (stats.total_active_days / days_since_start) * 100
        
        return {
            "success": True,
            "all_time_stats": {
                "total_active_days": stats.total_active_days or 0,
                "total_interactions": int(stats.total_interactions or 0),
                "average_interactions_per_day": round(float(stats.avg_interactions_per_day or 0), 1),
                "first_active_date": stats.first_active_date.isoformat() if stats.first_active_date else None,
                "last_active_date": stats.last_active_date.isoformat() if stats.last_active_date else None,
                "days_since_start": days_since_start,
                "overall_consistency_rate": round(overall_consistency, 1)
            },
            "current_streaks": {
                "current_streak": current_user.current_streak,
                "longest_streak": current_user.longest_streak,
                "last_interaction_date": current_user.last_interaction_date.isoformat() if current_user.last_interaction_date else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting streak stats for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve streak statistics"
        ) 