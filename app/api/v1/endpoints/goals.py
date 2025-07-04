from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_, desc
from datetime import datetime, timezone, timedelta

from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, Goal2Week, GoalLongTerm
from app.schemas.goal import (
    Goal as GoalSchema, 
    GoalCreate, 
    GoalUpdate, 
    GoalProgressUpdate,
    GoalTypeEnum,
    GoalDurationEnum,
    GoalStats,
    GoalsHistoryResponse,
    GoalHistoryEntry,
    CompletionStatsResponse,
    CompletionByType,
    CompletionByDuration
)
from app.core.security import log_security_event
from app.utils.goal_utils import calculate_2week_expiration, is_goal_expired

router = APIRouter()


def goal_to_schema(goal: Union[Goal2Week, GoalLongTerm]) -> GoalSchema:
    """Convert a database goal model to schema response."""
    goal_dict = {
        "id": goal.id,
        "name": goal.name,
        "goal_type": goal.goal_type,
        "duration": goal.duration,
        "target_value": goal.target_value,
        "current_value": goal.current_value,
        "is_completed": goal.is_completed,
        "progress_percentage": goal.progress_percentage,
        "user_id": goal.user_id,
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
        "completed_at": goal.completed_at,
        "expires_at": getattr(goal, 'expires_at', None)  # Only exists for Goal2Week
    }
    return GoalSchema(**goal_dict)


async def find_goal_by_id(db: AsyncSession, goal_id: int, user_id: int) -> Optional[Union[Goal2Week, GoalLongTerm]]:
    """Find a goal by ID across both tables, ensuring user ownership."""
    # Try 2-week goals first
    result = await db.execute(
        select(Goal2Week).where(
            and_(Goal2Week.id == goal_id, Goal2Week.user_id == user_id)
        )
    )
    goal = result.scalar_one_or_none()
    if goal:
        return goal
    
    # Try long-term goals
    result = await db.execute(
        select(GoalLongTerm).where(
            and_(GoalLongTerm.id == goal_id, GoalLongTerm.user_id == user_id)
        )
    )
    return result.scalar_one_or_none()


@router.get("", response_model=List[GoalSchema])
async def get_goals(
    request: Request,
    response: Response,
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    goal_type: Optional[GoalTypeEnum] = Query(None, description="Filter by goal type"),
    duration: Optional[GoalDurationEnum] = Query(None, description="Filter by duration type"),
    include_expired: bool = Query(False, description="Include expired 2-week goals"),
    include_completed: Optional[bool] = Query(None, description="Include completed goals (overrides default 24h behavior)"),
    completed_within_hours: Optional[int] = Query(None, ge=1, le=720, description="Include goals completed within X hours"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all goals for the current user with optional filters, including 24-hour completion visibility."""
    
    goals = []
    current_time = datetime.now(timezone.utc)
    
    # Determine completion visibility logic
    hours_cutoff = completed_within_hours if completed_within_hours is not None else 24
    cutoff_time = current_time - timedelta(hours=hours_cutoff)
    
    # Query 2-week goals if not filtering by long_term duration
    if duration != GoalDurationEnum.long_term:
        query_2week = select(Goal2Week).where(Goal2Week.user_id == current_user.id)
        
        # Handle completion filtering with 24-hour visibility
        if completed is not None:
            if completed:
                # If explicitly asking for completed goals, return all completed
                query_2week = query_2week.where(Goal2Week.is_completed == True)
            else:
                # If explicitly asking for non-completed goals, return only active
                query_2week = query_2week.where(Goal2Week.is_completed == False)
        else:
            # Default behavior: include active goals + goals completed within 24 hours
            if include_completed is True:
                # Include all completed goals
                pass  # No additional filtering
            elif include_completed is False:
                # Exclude all completed goals
                query_2week = query_2week.where(Goal2Week.is_completed == False)
            else:
                # Default: include active goals + recently completed (within specified hours)
                query_2week = query_2week.where(
                    or_(
                        Goal2Week.is_completed == False,  # Active goals
                        and_(
                            Goal2Week.is_completed == True,
                            Goal2Week.completed_at >= cutoff_time  # Recently completed
                        )
                    )
                )
        
        if goal_type is not None:
            query_2week = query_2week.where(Goal2Week.goal_type == goal_type.value)
        
        # Filter out expired goals unless specifically requested
        if not include_expired:
            query_2week = query_2week.where(Goal2Week.expires_at > current_time)
        
        result_2week = await db.execute(query_2week)
        goals_2week = result_2week.scalars().all()
        goals.extend(goals_2week)
    
    # Query long-term goals if not filtering by 2_week duration
    if duration != GoalDurationEnum.two_week:
        query_longterm = select(GoalLongTerm).where(GoalLongTerm.user_id == current_user.id)
        
        # Handle completion filtering with 24-hour visibility (same logic as 2-week)
        if completed is not None:
            if completed:
                query_longterm = query_longterm.where(GoalLongTerm.is_completed == True)
            else:
                query_longterm = query_longterm.where(GoalLongTerm.is_completed == False)
        else:
            # Default behavior: include active goals + goals completed within 24 hours
            if include_completed is True:
                # Include all completed goals
                pass  # No additional filtering
            elif include_completed is False:
                # Exclude all completed goals
                query_longterm = query_longterm.where(GoalLongTerm.is_completed == False)
            else:
                # Default: include active goals + recently completed (within specified hours)
                query_longterm = query_longterm.where(
                    or_(
                        GoalLongTerm.is_completed == False,  # Active goals
                        and_(
                            GoalLongTerm.is_completed == True,
                            GoalLongTerm.completed_at >= cutoff_time  # Recently completed
                        )
                    )
                )
        
        if goal_type is not None:
            query_longterm = query_longterm.where(GoalLongTerm.goal_type == goal_type.value)
        
        result_longterm = await db.execute(query_longterm)
        goals_longterm = result_longterm.scalars().all()
        goals.extend(goals_longterm)
    
    # Sort by creation date, most recent first
    goals.sort(key=lambda g: g.created_at, reverse=True)
    
    # Convert to schema responses
    return [goal_to_schema(goal) for goal in goals]


@router.post("", response_model=GoalSchema, status_code=status.HTTP_201_CREATED)
async def create_goal(
    goal_data: GoalCreate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new goal for the current user."""
    
    # Prepare goal data
    goal_dict = goal_data.dict()
    
    # Set target_value based on goal_type if not provided
    if goal_data.goal_type == GoalTypeEnum.percentage:
        goal_dict["target_value"] = 100
    elif goal_data.goal_type == GoalTypeEnum.checklist:
        goal_dict["target_value"] = 1
    # For counter type, target_value must be provided and validated by schema
    
    # Common fields
    goal_dict.update({
        "user_id": current_user.id,
        "current_value": 0,
        "is_completed": False,
        "duration": goal_data.duration.value,
        "goal_type": goal_data.goal_type.value
    })
    
    try:
        if goal_data.duration == GoalDurationEnum.two_week:
            # Generate server-side creation timestamp
            created_at = datetime.now(timezone.utc)
            goal_dict["expires_at"] = calculate_2week_expiration(created_at)
            
            goal = Goal2Week(**goal_dict)
            db.add(goal)
            await db.commit()
            await db.refresh(goal)
            
        else:  # long_term
            goal = GoalLongTerm(**goal_dict)
            db.add(goal)
            await db.commit()
            await db.refresh(goal)
        
        # Log security event
        table_name = "goals_2_week" if goal_data.duration == GoalDurationEnum.two_week else "goals_long_term"
        log_security_event(
            event_type="goal_created",
            details={
                "goal_id": goal.id,
                "name": goal.name,
                "goal_type": goal.goal_type,
                "duration": goal.duration,
                "target_value": goal.target_value,
                "table": table_name
            },
            level="info",
            user_id=current_user.id
        )
        
        return goal_to_schema(goal)
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create goal: {str(e)}"
        )


@router.get("/stats/summary", response_model=GoalStats)
async def get_goal_stats(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get goal statistics summary for the current user."""
    
    current_time = datetime.now(timezone.utc)
    
    # Get total goals from both tables
    total_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(Goal2Week.user_id == current_user.id)
    )
    total_2week = total_2week_result.scalar() or 0
    
    total_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(GoalLongTerm.user_id == current_user.id)
    )
    total_longterm = total_longterm_result.scalar() or 0
    
    total_goals = total_2week + total_longterm
    
    # Get completed goals from both tables
    completed_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(Goal2Week.user_id == current_user.id, Goal2Week.is_completed == True)
        )
    )
    completed_2week = completed_2week_result.scalar() or 0
    
    completed_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            and_(GoalLongTerm.user_id == current_user.id, GoalLongTerm.is_completed == True)
        )
    )
    completed_longterm = completed_longterm_result.scalar() or 0
    
    completed_goals = completed_2week + completed_longterm
    
    # Get goals by type from both tables
    # 2-week goals by type
    percentage_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(Goal2Week.user_id == current_user.id, Goal2Week.goal_type == "percentage")
        )
    )
    percentage_2week = percentage_2week_result.scalar() or 0
    
    counter_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(Goal2Week.user_id == current_user.id, Goal2Week.goal_type == "counter")
        )
    )
    counter_2week = counter_2week_result.scalar() or 0
    
    checklist_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(Goal2Week.user_id == current_user.id, Goal2Week.goal_type == "checklist")
        )
    )
    checklist_2week = checklist_2week_result.scalar() or 0
    
    # Long-term goals by type
    percentage_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            and_(GoalLongTerm.user_id == current_user.id, GoalLongTerm.goal_type == "percentage")
        )
    )
    percentage_longterm = percentage_longterm_result.scalar() or 0
    
    counter_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            and_(GoalLongTerm.user_id == current_user.id, GoalLongTerm.goal_type == "counter")
        )
    )
    counter_longterm = counter_longterm_result.scalar() or 0
    
    checklist_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            and_(GoalLongTerm.user_id == current_user.id, GoalLongTerm.goal_type == "checklist")
        )
    )
    checklist_longterm = checklist_longterm_result.scalar() or 0
    
    # Combine totals by type
    percentage_goals = percentage_2week + percentage_longterm
    counter_goals = counter_2week + counter_longterm
    checklist_goals = checklist_2week + checklist_longterm
    
    # Get active 2-week goals (non-expired, non-completed)
    active_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(
                Goal2Week.user_id == current_user.id,
                Goal2Week.is_completed == False,
                Goal2Week.expires_at > current_time
            )
        )
    )
    active_2_week_goals = active_2week_result.scalar() or 0
    
    # Long term goals (all of them, since they don't expire)
    long_term_goals = total_longterm
    
    # Calculate completion rate
    completion_rate = (completed_goals / total_goals * 100) if total_goals > 0 else 0.0
    
    return GoalStats(
        total_goals=total_goals,
        completed_goals=completed_goals,
        percentage_goals=percentage_goals,
        counter_goals=counter_goals,
        checklist_goals=checklist_goals,
        active_2_week_goals=active_2_week_goals,
        long_term_goals=long_term_goals,
        completion_rate=round(completion_rate, 1)
    )


async def _get_goals_history_logic(
    db: AsyncSession,
    user_id: int,
    days_back: int,
    limit: Optional[int],
    offset: Optional[int],
    goal_type: Optional[GoalTypeEnum] = None,
    duration: Optional[GoalDurationEnum] = None
) -> GoalsHistoryResponse:
    """
    Core logic for fetching paginated goals history.
    
    Fetches completed goals from both Goal2Week and GoalLongTerm tables,
    excluding those completed within the last 24 hours to maintain UI consistency.
    """
    current_time = datetime.now(timezone.utc)
    start_date = current_time - timedelta(days=days_back)
    cutoff_time = current_time - timedelta(hours=24)  # 24-hour exclusion
    
    goals = []
    
    # Query 2-week goals if not filtering by long_term duration
    if duration != GoalDurationEnum.long_term:
        query_2week = select(Goal2Week).where(
            and_(
                Goal2Week.user_id == user_id,
                Goal2Week.is_completed == True,
                Goal2Week.completed_at >= start_date,
                Goal2Week.completed_at < cutoff_time  # Exclude last 24 hours
            )
        )
        
        if goal_type is not None:
            query_2week = query_2week.where(Goal2Week.goal_type == goal_type.value)
        
        result_2week = await db.execute(query_2week)
        goals_2week = result_2week.scalars().all()
        goals.extend(goals_2week)
    
    # Query long-term goals if not filtering by 2_week duration
    if duration != GoalDurationEnum.two_week:
        query_longterm = select(GoalLongTerm).where(
            and_(
                GoalLongTerm.user_id == user_id,
                GoalLongTerm.is_completed == True,
                GoalLongTerm.completed_at >= start_date,
                GoalLongTerm.completed_at < cutoff_time  # Exclude last 24 hours
            )
        )
        
        if goal_type is not None:
            query_longterm = query_longterm.where(GoalLongTerm.goal_type == goal_type.value)
        
        result_longterm = await db.execute(query_longterm)
        goals_longterm = result_longterm.scalars().all()
        goals.extend(goals_longterm)
    
    # Sorting: Sort by completed_at in descending order (newest first) BEFORE pagination
    goals.sort(key=lambda g: g.completed_at, reverse=True)
    
    # Get total count before pagination
    total_count = len(goals)
    
    # Pagination: Apply limit and offset to the sorted list
    start_idx = offset if offset is not None else 0
    end_idx = start_idx + limit if limit is not None else len(goals)
    paginated_goals = goals[start_idx:end_idx]
    
    # Convert to history entry schemas with dynamic calculation
    history_entries = []
    for goal in paginated_goals:
        # Dynamic Calculation: completion_days with minimum 1
        completion_days = (goal.completed_at - goal.created_at).days
        completion_days = max(1, completion_days)  # Minimum 1 day
        
        history_entry = GoalHistoryEntry(
            id=goal.id,
            name=goal.name,
            goal_type=goal.goal_type,  # String value
            duration=goal.duration,    # String value
            target_value=goal.target_value,
            current_value=goal.current_value,
            completed_at=goal.completed_at.isoformat() + "Z",  # Convert to ISO string
            completion_days=completion_days,
            created_at=goal.created_at.isoformat() + "Z"       # Convert to ISO string
        )
        history_entries.append(history_entry)
    
    # Calculate date range from actual results, formatted as ISO strings
    if history_entries:
        actual_start = min(goal.completed_at for goal in paginated_goals)
        actual_end = max(goal.completed_at for goal in paginated_goals)
    else:
        actual_start = start_date
        actual_end = cutoff_time
    
    return GoalsHistoryResponse(
        goals=history_entries,
        total_count=total_count,
        date_range={
            "start": actual_start.isoformat(),
            "end": actual_end.isoformat()
        }
    )


@router.get("/history", response_model=GoalsHistoryResponse)
async def get_goals_history(
    request: Request,
    response: Response,
    days_back: int = Query(90, ge=1, le=365, description="Days to look back (1-365)"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum goals to return (1-100)"),
    offset: Optional[int] = Query(None, ge=0, description="Pagination offset"),
    goal_type: Optional[GoalTypeEnum] = Query(None, description="Filter by goal type"),
    duration: Optional[GoalDurationEnum] = Query(None, description="Filter by duration"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> GoalsHistoryResponse:
    """
    Get paginated history of completed goals.
    
    Implements the Goals Completion History system with:
    - 24-hour exclusion of recently completed goals
    - Dual table querying (2-week and long-term goals)
    - Proper sorting by completion date
    - Dynamic completion days calculation
    """
    try:
        return await _get_goals_history_logic(
            db=db,
            user_id=current_user.id,
            days_back=days_back,
            limit=limit,
            offset=offset,
            goal_type=goal_type,
            duration=duration
        )
    except Exception as e:
        # Error Handling: Return 500 with generic message for unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching goal history"
        )


@router.get("/stats/completion", response_model=CompletionStatsResponse)
async def get_completion_stats(
    request: Request,
    response: Response,
    days_back: int = Query(30, ge=1, le=365, description="Number of days back to calculate statistics"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get completion statistics for the specified time period."""
    
    current_time = datetime.now(timezone.utc)
    start_date = current_time - timedelta(days=days_back)
    
    # Get completed goals from both tables within the time period
    completed_2week_result = await db.execute(
        select(Goal2Week).where(
            and_(
                Goal2Week.user_id == current_user.id,
                Goal2Week.is_completed == True,
                Goal2Week.completed_at >= start_date
            )
        )
    )
    completed_2week_goals = completed_2week_result.scalars().all()
    
    completed_longterm_result = await db.execute(
        select(GoalLongTerm).where(
            and_(
                GoalLongTerm.user_id == current_user.id,
                GoalLongTerm.is_completed == True,
                GoalLongTerm.completed_at >= start_date
            )
        )
    )
    completed_longterm_goals = completed_longterm_result.scalars().all()
    
    # Combine completed goals
    all_completed_goals = list(completed_2week_goals) + list(completed_longterm_goals)
    total_completed = len(all_completed_goals)
    
    # Calculate average completion days
    if all_completed_goals:
        completion_days_list = []
        for goal in all_completed_goals:
            # Use completed_at if available, otherwise fall back to updated_at
            completion_time = getattr(goal, 'completed_at', None) or goal.updated_at
            completion_days = (completion_time - goal.created_at).days
            completion_days_list.append(completion_days)
        avg_completion_days = sum(completion_days_list) / len(completion_days_list)
    else:
        avg_completion_days = 0.0
    
    # Get all goals created within the time period for completion rate calculation
    created_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(
                Goal2Week.user_id == current_user.id,
                Goal2Week.created_at >= start_date
            )
        )
    )
    created_2week_count = created_2week_result.scalar() or 0
    
    created_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            and_(
                GoalLongTerm.user_id == current_user.id,
                GoalLongTerm.created_at >= start_date
            )
        )
    )
    created_longterm_count = created_longterm_result.scalar() or 0
    
    total_created = created_2week_count + created_longterm_count
    
    # Calculate completion rate (safely handle division by zero)
    completion_rate = (total_completed / total_created * 100) if total_created > 0 else 0.0
    
    # Calculate breakdown by type
    by_type = CompletionByType()
    for goal in all_completed_goals:
        if goal.goal_type == "percentage":
            by_type.percentage += 1
        elif goal.goal_type == "counter":
            by_type.counter += 1
        elif goal.goal_type == "checklist":
            by_type.checklist += 1
    
    # Calculate breakdown by duration
    by_duration = CompletionByDuration()
    by_duration.two_week = len(completed_2week_goals)
    by_duration.long_term = len(completed_longterm_goals)
    
    return CompletionStatsResponse(
        total_completed=total_completed,
        avg_completion_days=round(avg_completion_days, 1),
        completion_rate=round(completion_rate, 1),
        by_type=by_type,
        by_duration=by_duration
    )


@router.get("/{goal_id}", response_model=GoalSchema)
async def get_goal(
    goal_id: int,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific goal by ID."""
    
    goal = await find_goal_by_id(db, goal_id, current_user.id)
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    return goal_to_schema(goal)


@router.put("/{goal_id}", response_model=GoalSchema)
async def update_goal(
    goal_id: int,
    goal_data: GoalUpdate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a specific goal's basic information (name and current_value only)."""
    
    goal = await find_goal_by_id(db, goal_id, current_user.id)
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    # Update fields (only name and current_value allowed)
    update_data = goal_data.dict(exclude_unset=True)
    
    # Validate current_value doesn't exceed target
    if "current_value" in update_data:
        new_current = update_data["current_value"]
        if new_current > goal.target_value:
            update_data["current_value"] = goal.target_value
        
        # Update completion status
        update_data["is_completed"] = update_data["current_value"] >= goal.target_value
    
    for field, value in update_data.items():
        setattr(goal, field, value)
    
    await db.commit()
    await db.refresh(goal)
    
    # Log security event
    table_name = "goals_2_week" if isinstance(goal, Goal2Week) else "goals_long_term"
    log_security_event(
        event_type="goal_updated",
        details={
            "goal_id": goal.id, 
            "updated_fields": list(update_data.keys()),
            "table": table_name
        },
        level="info",
        user_id=current_user.id
    )
    
    return goal_to_schema(goal)


@router.patch("/{goal_id}/progress", response_model=GoalSchema)
async def update_goal_progress(
    goal_id: int,
    progress_data: GoalProgressUpdate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update goal progress based on goal type."""
    
    goal = await find_goal_by_id(db, goal_id, current_user.id)
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    old_value = goal.current_value
    
    # Handle different goal types
    if goal.goal_type == "checklist":
        # Checklist: toggle completion or set specific state
        if progress_data.complete is not None:
            goal.current_value = 1 if progress_data.complete else 0
        else:
            # Toggle if no specific state provided
            goal.current_value = 1 if goal.current_value == 0 else 0
            
    elif goal.goal_type == "counter":
        # Counter: increment or set new value
        if progress_data.increment is not None:
            goal.current_value = min(goal.target_value, goal.current_value + progress_data.increment)
        elif progress_data.new_value is not None:
            goal.current_value = min(goal.target_value, progress_data.new_value)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Counter goals require either 'increment' or 'new_value'"
            )
            
    elif goal.goal_type == "percentage":
        # Percentage: set new value (0-100)
        if progress_data.new_value is not None:
            goal.current_value = min(100, max(0, progress_data.new_value))
        elif progress_data.increment is not None:
            goal.current_value = min(100, goal.current_value + progress_data.increment)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Percentage goals require either 'increment' or 'new_value'"
            )
    
    # Update completion status
    was_completed = goal.is_completed
    goal.is_completed = goal.current_value >= goal.target_value
    
    # Set completed_at timestamp when goal is newly completed
    if goal.is_completed and not was_completed:
        goal.completed_at = datetime.now(timezone.utc)
        
        # Log goal completion event with calculated days to complete
        completion_days = (goal.completed_at - goal.created_at).days
        completion_days = max(1, completion_days)  # Minimum 1 day
        
        log_security_event(
            event_type="goal_completed",
            details={
                "goal_id": goal.id,
                "name": goal.name,
                "goal_type": goal.goal_type,
                "duration": goal.duration,
                "target_value": goal.target_value,
                "completion_days": completion_days,
                "completed_at": goal.completed_at.isoformat(),
                "table": "goals_2_week" if isinstance(goal, Goal2Week) else "goals_long_term"
            },
            level="info",
            user_id=current_user.id
        )
    
    await db.commit()
    await db.refresh(goal)
    
    # Log security event
    table_name = "goals_2_week" if isinstance(goal, Goal2Week) else "goals_long_term"
    log_security_event(
        event_type="goal_progress_updated",
        details={
            "goal_id": goal.id,
            "goal_type": goal.goal_type,
            "duration": goal.duration,
            "old_value": old_value,
            "new_value": goal.current_value,
            "is_completed": goal.is_completed,
            "table": table_name
        },
        level="info",
        user_id=current_user.id
    )
    
    return goal_to_schema(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: int,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific goal."""
    
    goal = await find_goal_by_id(db, goal_id, current_user.id)
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    # Store info for logging before deletion
    goal_info = {
        "goal_id": goal_id,
        "name": goal.name,
        "goal_type": goal.goal_type,
        "duration": goal.duration,
        "table": "goals_2_week" if isinstance(goal, Goal2Week) else "goals_long_term"
    }
    
    await db.delete(goal)
    await db.commit()
    
    # Log security event
    log_security_event(
        event_type="goal_deleted",
        details=goal_info,
        level="info",
        user_id=current_user.id
    ) 