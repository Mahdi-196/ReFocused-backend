from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from datetime import datetime, timezone

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
    GoalStats
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all goals for the current user with optional filters."""
    
    goals = []
    current_time = datetime.now(timezone.utc)
    
    # Query 2-week goals if not filtering by long_term duration
    if duration != GoalDurationEnum.long_term:
        query_2week = select(Goal2Week).where(Goal2Week.user_id == current_user.id)
        
        if completed is not None:
            query_2week = query_2week.where(Goal2Week.is_completed == completed)
        
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
        
        if completed is not None:
            query_longterm = query_longterm.where(GoalLongTerm.is_completed == completed)
        
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
        "is_completed": False
    })
    
    # Create goal in appropriate table based on duration
    if goal_data.duration == GoalDurationEnum.two_week:
        # Calculate expiration for 2-week goals
        created_at = datetime.now(timezone.utc)
        expires_at = calculate_2week_expiration(created_at)
        goal_dict["expires_at"] = expires_at
        
        db_goal = Goal2Week(**goal_dict)
    else:
        # Long-term goal
        db_goal = GoalLongTerm(**goal_dict)
    
    db.add(db_goal)
    await db.commit()
    await db.refresh(db_goal)
    
    # Log security event
    log_security_event(
        event_type="goal_created",
        details={
            "goal_id": db_goal.id, 
            "name": db_goal.name,
            "goal_type": db_goal.goal_type,
            "duration": db_goal.duration,
            "target_value": db_goal.target_value,
            "table": "goals_2_week" if isinstance(db_goal, Goal2Week) else "goals_long_term"
        },
        level="info",
        user_id=current_user.id
    )
    
    return goal_to_schema(db_goal)


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
    goal.is_completed = goal.current_value >= goal.target_value
    
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


@router.get("/stats/summary", response_model=GoalStats)
async def get_goal_stats(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get goal statistics for the current user."""
    
    current_time = datetime.now(timezone.utc)
    
    # Get counts from 2-week goals (excluding expired by default)
    total_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(Goal2Week.user_id == current_user.id, Goal2Week.expires_at > current_time)
        )
    )
    active_2week_total = total_2week_result.scalar() or 0
    
    completed_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(
                Goal2Week.user_id == current_user.id,
                Goal2Week.is_completed == True,
                Goal2Week.expires_at > current_time
            )
        )
    )
    completed_2week = completed_2week_result.scalar() or 0
    
    # Active 2-week goals (non-expired, non-completed)
    active_2week_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            and_(
                Goal2Week.user_id == current_user.id,
                Goal2Week.is_completed == False,
                Goal2Week.expires_at > current_time
            )
        )
    )
    active_2week_goals = active_2week_result.scalar() or 0
    
    # Get counts from long-term goals
    total_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(GoalLongTerm.user_id == current_user.id)
    )
    long_term_goals = total_longterm_result.scalar() or 0
    
    completed_longterm_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            and_(GoalLongTerm.user_id == current_user.id, GoalLongTerm.is_completed == True)
        )
    )
    completed_longterm = completed_longterm_result.scalar() or 0
    
    # Get counts by goal type across both tables
    type_counts_2week = await db.execute(
        select(Goal2Week.goal_type, func.count(Goal2Week.id)).where(
            and_(Goal2Week.user_id == current_user.id, Goal2Week.expires_at > current_time)
        ).group_by(Goal2Week.goal_type)
    )
    type_counts_2week_dict = {row[0]: row[1] for row in type_counts_2week.fetchall()}
    
    type_counts_longterm = await db.execute(
        select(GoalLongTerm.goal_type, func.count(GoalLongTerm.id)).where(
            GoalLongTerm.user_id == current_user.id
        ).group_by(GoalLongTerm.goal_type)
    )
    type_counts_longterm_dict = {row[0]: row[1] for row in type_counts_longterm.fetchall()}
    
    # Aggregate totals
    total_goals = active_2week_total + long_term_goals
    completed_goals = completed_2week + completed_longterm
    percentage_goals = type_counts_2week_dict.get("percentage", 0) + type_counts_longterm_dict.get("percentage", 0)
    counter_goals = type_counts_2week_dict.get("counter", 0) + type_counts_longterm_dict.get("counter", 0)
    checklist_goals = type_counts_2week_dict.get("checklist", 0) + type_counts_longterm_dict.get("checklist", 0)
    
    # Calculate completion rate
    completion_rate = (completed_goals / total_goals * 100) if total_goals > 0 else 0.0
    
    return GoalStats(
        total_goals=total_goals,
        completed_goals=completed_goals,
        percentage_goals=percentage_goals,
        counter_goals=counter_goals,
        checklist_goals=checklist_goals,
        active_2_week_goals=active_2week_goals,
        long_term_goals=long_term_goals,
        completion_rate=completion_rate
    ) 