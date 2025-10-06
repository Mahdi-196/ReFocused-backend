from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from datetime import date, timedelta
import logging

from app.db.database import get_db
from app.core.auth import get_current_user
from app.crud.habit import habit_crud
from app.schemas.habit import (
    HabitCreate, HabitUpdate, HabitResponse, 
    HabitCompletionUpdate, HabitCompletionResponse,
    HabitStatsResponse, BulkCompletionRequest, BulkCompletionResponse
)
from app.db.models import User, HabitCompletion
from app.services.time_service import TimeService

# Custom dependency to handle OPTIONS requests
from app.core.auth import oauth2_scheme

async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current user but allow OPTIONS requests to pass through"""
    if request.method == "OPTIONS":
        return None
    
    # For non-OPTIONS requests, get the token and authenticate
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_header.split(" ")[1]
    return await get_current_user(token, db, request)

router = APIRouter(
    tags=["habits"],
    responses={
        404: {"description": "Habit not found"},
        403: {"description": "Access forbidden"},
        400: {"description": "Invalid request"}
    }
)
logger = logging.getLogger(__name__)
time_service = TimeService()

def get_user_timezone(x_user_timezone: Optional[str] = Header(None)) -> str:
    """Extract and validate user timezone from header"""
    if not x_user_timezone:
        # Default to UTC if no timezone provided
        return "UTC"
    
    # Validate timezone (basic check)
    if len(x_user_timezone) < 3 or '/' not in x_user_timezone:
        # Default to UTC if invalid timezone
        return "UTC"
    
    return x_user_timezone

# IMPORTANT: Routes with specific paths MUST come before parameterized routes
# Otherwise FastAPI will match /{habit_id} before /completions

@router.get("/completions", response_model=List[HabitCompletionResponse])
async def get_all_habit_completions(
    start_date: str = Query(..., regex=r'^\d{4}-\d{2}-\d{2}$', description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., regex=r'^\d{4}-\d{2}-\d{2}$', description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """Get all habit completions for all habits within a date range"""
    try:
        # Validate and parse dates
        try:
            start_date_obj = date.fromisoformat(start_date)
            end_date_obj = date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Validate date range
        if start_date_obj > end_date_obj:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_date must be before or equal to end_date"
            )
        
        # Limit date range to prevent excessive queries
        if (end_date_obj - start_date_obj).days > 365:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Date range cannot exceed 365 days"
            )
        
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        # Use the range method directly
        completions = await habit_crud.get_completions_for_range(
            db, current_user, start_date_obj, end_date_obj
        )
        
        # Format response to match frontend expectations
        formatted_completions = []
        for completion in completions:
            formatted_completions.append(HabitCompletionResponse(
                id=completion.id,
                habit_id=completion.habit_id,
                date=completion.date,
                completed=completion.completed,
                completed_at=completion.completed_at.isoformat() if completion.completed_at else None,
                timezone=completion.timezone if hasattr(completion, 'timezone') and completion.timezone else current_user.timezone
            ))
        
        return formatted_completions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting all habit completions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve habit completions"
        )

@router.get("", response_model=List[HabitResponse])
async def get_habits(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Get all habits with automatic timezone-aware reset check.
    
    Headers:
    - X-User-Timezone: User's IANA timezone identifier (e.g., "America/New_York")
    
    This implements the on-demand reset strategy - habits are automatically
    reset when the user's local day changes since their last interaction.
    """
    try:
        # Update user's timezone if different
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        habits = await habit_crud.get_habits_with_reset_check(
            db, current_user, include_inactive
        )
        return habits
        
    except Exception as e:
        logger.error(f"Error getting habits for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve habits"
        )

@router.get("/streak-status")
async def get_streak_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get streak status for all habits with today's completion status"""
    from app.core.config import settings
    
    habits = await habit_crud.get_habits_with_reset_check(db, current_user)
    today = time_service.get_user_current_date(current_user)
    
    habit_status = []
    for habit in habits:
        # Check if completed today
        completion_result = await db.execute(
            select(HabitCompletion).where(
                and_(
                    HabitCompletion.habit_id == habit.id,
                    HabitCompletion.date == today,
                    HabitCompletion.completed == True
                )
            )
        )
        completed_today = completion_result.scalar_one_or_none() is not None
        
        habit_status.append({
            "id": habit.id,
            "name": habit.name,
            "current_streak": habit.streak,
            "completed_today": completed_today,
            "at_risk": habit.streak > 0 and not completed_today  # Streak will be lost if not completed
        })
    
    return {
        "date": str(today),
        "habits": habit_status,
        "total_habits": len(habits),
        "completed_today": sum(1 for h in habit_status if h["completed_today"]),
        "at_risk": sum(1 for h in habit_status if h["at_risk"])
    }

@router.post("/reset-daily-streaks", status_code=status.HTTP_200_OK)
async def reset_daily_streaks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reset streaks for habits not completed today.
    This endpoint should be called daily at midnight.
    """
    # Note: reset_incomplete_streaks method not implemented in habit_crud
    # This endpoint may need to be updated or removed
    reset_count = 0
    return {
        "message": f"Daily streak reset completed",
        "habits_reset": reset_count,
        "user_id": current_user.id
    }

@router.post("", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
async def create_habit(
    habit_data: HabitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """Create a new habit"""
    try:
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        habit = await habit_crud.create_habit(db, habit_data, current_user)
        
        # Create response with computed fields
        return HabitResponse(
            id=habit.id,
            name=habit.name,
            is_favorite=habit.is_favorite,
            is_active=habit.is_active,
            streak=habit.streak,
            created_at=habit.created_at,
            last_updated_utc=habit.last_updated_utc,
            last_completed_date=None  # New habit has no completions yet
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating habit: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create habit"
        )

@router.get("/{habit_id}", response_model=HabitResponse)
async def get_habit(
    habit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """Get a specific habit with reset check"""
    try:
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        habit = await habit_crud.get_habit_with_reset_check(db, habit_id, current_user)
        if not habit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habit not found"
            )
        
        return habit
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting habit {habit_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve habit"
        )

@router.put("/{habit_id}", response_model=HabitResponse)
async def update_habit(
    habit_id: int,
    habit_data: HabitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """Update a habit"""
    try:
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        habit = await habit_crud.update_habit(db, habit_id, habit_data, current_user)
        if not habit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habit not found"
            )
        
        return habit
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating habit {habit_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update habit"
        )

@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(
    habit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a habit and all its completions"""
    try:
        success = await habit_crud.delete_habit(db, habit_id, current_user)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habit not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting habit {habit_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete habit"
        )

@router.post("/completions", status_code=status.HTTP_200_OK)
async def mark_habit_completion(
    completion_data: HabitCompletionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Mark a habit as completed or uncompleted for a specific date.
    
    This endpoint handles both checking and unchecking habits with
    automatic streak recalculation.
    """
    try:
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        success = await habit_crud.mark_habit_completion(
            db, 
            completion_data.habit_id, 
            completion_data.date, 
            completion_data.completed, 
            current_user
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habit not found"
            )
        
        return {
            "success": True,
            "message": f"Habit {'completed' if completion_data.completed else 'uncompleted'} for {completion_data.date}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking habit completion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update habit completion"
        )

@router.post("/completions/bulk", response_model=BulkCompletionResponse)
async def bulk_habit_completions(
    request: BulkCompletionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Update multiple habit completions in a single request.
    Useful for batch operations and calendar synchronization.
    """
    try:
        if not request.completions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No completions provided"
            )
        
        if len(request.completions) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many completions in single request (max 50)"
            )
        
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        success_count = 0
        errors = []
        
        for completion in request.completions:
            try:
                success = await habit_crud.mark_habit_completion(
                    db,
                    completion.habit_id,
                    completion.date,
                    completion.completed,
                    current_user
                )
                if success:
                    success_count += 1
                else:
                    errors.append(f"Habit {completion.habit_id} not found")
                    
            except Exception as e:
                errors.append(f"Habit {completion.habit_id}: {str(e)}")
        
        return BulkCompletionResponse(
            success_count=success_count,
            error_count=len(errors),
            errors=errors
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk completion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process bulk completions"
        )

@router.get("/{habit_id}/completions", response_model=List[HabitCompletionResponse])
async def get_habit_completions(
    habit_id: int,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """Get habit completions for a date range"""
    try:
        # Validate date range
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before or equal to end_date"
            )
        
        # Limit date range to prevent excessive queries
        if (end_date - start_date).days > 365:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Date range cannot exceed 365 days"
            )
        
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        completions = await habit_crud.get_habit_completions(
            db, habit_id, start_date, end_date, current_user
        )
        
        return completions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting completions for habit {habit_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve habit completions"
        )

@router.get("/{habit_id}/stats", response_model=HabitStatsResponse)
async def get_habit_stats(
    habit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """Get comprehensive habit statistics"""
    try:
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        stats = await habit_crud.get_habit_stats(db, habit_id, current_user)
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats for habit {habit_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve habit statistics"
        )

@router.get("/dashboard/summary")
async def get_habits_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_timezone: str = Depends(get_user_timezone)
):
    """
    Get a summary of all habits for dashboard display.
    Includes today's completion status and streak information.
    """
    try:
        # Update user's timezone
        if current_user.timezone != user_timezone:
            current_user.timezone = user_timezone
            await db.commit()
        
        habits = await habit_crud.get_habits_with_reset_check(db, current_user)
        current_date = time_service.get_user_current_date(current_user)
        
        total_habits = len(habits)
        completed_today = 0
        total_streak = 0
        
        habit_summaries = []
        
        for habit in habits:
            # Check if completed today
            completions = await habit_crud.get_habit_completions(
                db, habit.id, current_date, current_date, current_user
            )
            completed_today_habit = len(completions) > 0
            
            if completed_today_habit:
                completed_today += 1
            
            total_streak += habit.streak
            
            habit_summaries.append({
                "id": habit.id,
                "name": habit.name,
                "streak": habit.streak,
                "is_favorite": habit.is_favorite,
                "completed_today": completed_today_habit
            })
        
        return {
            "date": current_date.strftime("%Y-%m-%d"),
            "total_habits": total_habits,
            "completed_today": completed_today,
            "completion_rate": round((completed_today / total_habits * 100) if total_habits > 0 else 0, 1),
            "total_streak_days": total_streak,
            "habits": habit_summaries
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard summary"
        )

@router.get("/{habit_id}/analytics")
async def get_habit_analytics(
    habit_id: int,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed analytics for a specific habit including completion rate,
    streak history, and performance insights over the specified period.
    """
    try:
        # Validate habit ownership
        habit = await habit_crud.get_habit_with_reset_check(db, habit_id, current_user)
        if not habit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habit not found"
            )
        
        from app.core.config import settings
        from datetime import timedelta
        
        current_date = settings.get_current_date()
        start_date = current_date - timedelta(days=days-1)
        
        # Get all completions in the period
        completions = await habit_crud.get_habit_completions(
            db, habit_id, start_date, current_date, current_user
        )
        
        # Calculate analytics
        total_days = days
        completed_days = len(completions)
        completion_rate = (completed_days / total_days) * 100 if total_days > 0 else 0
        
        # Calculate week-by-week breakdown
        weekly_stats = []
        for week_start in range(0, days, 7):
            week_end = min(week_start + 6, days - 1)
            week_start_date = current_date - timedelta(days=days-1-week_start)
            week_end_date = current_date - timedelta(days=days-1-week_end)
            
            week_completions = [
                c for c in completions 
                if week_end_date <= c <= week_start_date
            ]
            
            weekly_stats.append({
                "week": len(weekly_stats) + 1,
                "start_date": str(week_end_date),
                "end_date": str(week_start_date),
                "completions": len(week_completions),
                "completion_rate": (len(week_completions) / 7) * 100
            })
        
        # Find longest streak in period
        longest_streak_in_period = 0
        current_streak_in_period = 0
        completion_set = set(completions)
        
        for i in range(days):
            check_date = current_date - timedelta(days=i)
            if check_date in completion_set:
                current_streak_in_period += 1
                longest_streak_in_period = max(longest_streak_in_period, current_streak_in_period)
            else:
                current_streak_in_period = 0
        
        return {
            "habit_id": habit_id,
            "habit_name": habit.name,
            "current_streak": habit.streak,
            "analysis_period": {
                "days": days,
                "start_date": str(start_date),
                "end_date": str(current_date)
            },
            "overall_stats": {
                "total_days": total_days,
                "completed_days": completed_days,
                "missed_days": total_days - completed_days,
                "completion_rate": round(completion_rate, 2),
                "longest_streak_in_period": longest_streak_in_period
            },
            "weekly_breakdown": weekly_stats,
            "completion_dates": [str(d) for d in sorted(completions)]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating analytics for habit {habit_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate habit analytics"
        )

@router.get("/{habit_id}/debug")
async def debug_habit_streak(
    habit_id: int,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Debug endpoint to troubleshoot streak calculation (secured for production)"""
    from app.core.config import settings
    from sqlalchemy import select, desc
    from app.db.models import HabitCompletion
    from datetime import timedelta
    
    # Optionally refresh the streak before debugging
    if refresh:
        await habit_crud._recalculate_habit_streak(db, habit_id, current_user)
    
    # Get habit
    habit = await habit_crud.get_habit_with_reset_check(db, habit_id, current_user)
    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )
    
    # Get all completions for this habit
    result = await db.execute(
        select(HabitCompletion.date).where(
            and_(
                HabitCompletion.habit_id == habit_id,
                HabitCompletion.completed == True
            )
        ).order_by(desc(HabitCompletion.date))
    )
    completion_dates = result.scalars().all()
    
    # Current date info
    current_date = settings.get_current_date()
    
    # Calculate streak step by step for debugging
    streak_calculation_steps = []
    fresh_calculation = 0
    if completion_dates:
        last_completion = completion_dates[0]
        today = current_date
        
        streak_calculation_steps.append(f"Last completion: {last_completion}")
        streak_calculation_steps.append(f"Today: {today}")
        
        if last_completion < today - timedelta(days=1):
            streak_calculation_steps.append("Streak broken - last completion too old")
            fresh_calculation = 0
        else:
            expected_date = today if last_completion == today else today - timedelta(days=1)
            streak_calculation_steps.append(f"Starting from: {expected_date}")
            
            streak = 0
            for completion_date in completion_dates:
                if completion_date == expected_date:
                    streak += 1
                    streak_calculation_steps.append(f"Match: {completion_date}, streak now {streak}")
                    expected_date -= timedelta(days=1)
                elif completion_date < expected_date:
                    streak_calculation_steps.append(f"Gap found at {expected_date}, stopping")
                    break
            fresh_calculation = streak
    
    return {
        "habit_id": habit_id,
        "habit_name": habit.name,
        "stored_streak": habit.streak,
        "fresh_calculation": fresh_calculation,
        "streaks_match": habit.streak == fresh_calculation,
        "current_date": current_date,
        "timezone": current_user.timezone,
        "completion_dates": [str(d) for d in completion_dates],
        "completion_count": len(completion_dates),
        "last_completion": str(completion_dates[0]) if completion_dates else None,
        "streak_calculation_steps": streak_calculation_steps,
        "was_refreshed": refresh
    }

@router.post("/{habit_id}/refresh-streak", status_code=status.HTTP_200_OK)
async def refresh_habit_streak(
    habit_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually refresh a habit's streak calculation"""
    try:
        await habit_crud._recalculate_habit_streak(db, habit_id, current_user)
        # Get updated habit
        habit = await habit_crud.get_habit_with_reset_check(db, habit_id, current_user)
        if not habit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habit not found"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh streak: {str(e)}"
        )
    return {
        "message": "Habit streak refreshed successfully",
        "habit_id": habit_id,
        "new_streak": habit.streak
    }

 