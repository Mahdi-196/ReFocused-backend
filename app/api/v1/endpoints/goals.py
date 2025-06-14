from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, Goal
from app.schemas.goal import Goal as GoalSchema, GoalCreate, GoalUpdate, PriorityEnum
from app.core.security import log_security_event

router = APIRouter()


@router.get("", response_model=List[GoalSchema])
async def get_goals(
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    priority: Optional[PriorityEnum] = Query(None, description="Filter by priority"),
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all goals for the current user with optional filters."""
    
    # Build query
    query = select(Goal).where(Goal.user_id == current_user.id)
    
    if completed is not None:
        query = query.where(Goal.is_completed == completed)
    
    if priority is not None:
        query = query.where(Goal.priority == priority.value)
    
    if category is not None:
        query = query.where(Goal.category.ilike(f"%{category}%"))
    
    # Order by creation date, most recent first
    query = query.order_by(Goal.created_at.desc())
    
    result = await db.execute(query)
    goals = result.scalars().all()
    
    return goals


@router.post("", response_model=GoalSchema, status_code=status.HTTP_201_CREATED)
async def create_goal(
    goal_data: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new goal for the current user."""
    
    # Create new goal
    db_goal = Goal(
        **goal_data.dict(),
        user_id=current_user.id
    )
    
    db.add(db_goal)
    await db.commit()
    await db.refresh(db_goal)
    
    # Log security event
    log_security_event(
        event_type="goal_created",
        details={"goal_id": db_goal.id, "title": db_goal.title},
        level="info",
        user_id=current_user.id
    )
    
    return db_goal


@router.get("/{goal_id}", response_model=GoalSchema)
async def get_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific goal by ID."""
    
    result = await db.execute(
        select(Goal).where(
            and_(Goal.id == goal_id, Goal.user_id == current_user.id)
        )
    )
    goal = result.scalar_one_or_none()
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    return goal


@router.put("/{goal_id}", response_model=GoalSchema)
async def update_goal(
    goal_id: int,
    goal_data: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a specific goal."""
    
    result = await db.execute(
        select(Goal).where(
            and_(Goal.id == goal_id, Goal.user_id == current_user.id)
        )
    )
    goal = result.scalar_one_or_none()
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    # Update fields
    update_data = goal_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(goal, field, value)
    
    await db.commit()
    await db.refresh(goal)
    
    # Log security event
    log_security_event(
        event_type="goal_updated",
        details={"goal_id": goal.id, "updated_fields": list(update_data.keys())},
        level="info",
        user_id=current_user.id
    )
    
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific goal."""
    
    result = await db.execute(
        select(Goal).where(
            and_(Goal.id == goal_id, Goal.user_id == current_user.id)
        )
    )
    goal = result.scalar_one_or_none()
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    await db.delete(goal)
    await db.commit()
    
    # Log security event
    log_security_event(
        event_type="goal_deleted",
        details={"goal_id": goal_id, "title": goal.title},
        level="info",
        user_id=current_user.id
    )


@router.patch("/{goal_id}/complete", response_model=GoalSchema)
async def toggle_goal_completion(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toggle the completion status of a goal."""
    
    result = await db.execute(
        select(Goal).where(
            and_(Goal.id == goal_id, Goal.user_id == current_user.id)
        )
    )
    goal = result.scalar_one_or_none()
    
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )
    
    # Toggle completion status
    goal.is_completed = not goal.is_completed
    
    await db.commit()
    await db.refresh(goal)
    
    # Log security event
    log_security_event(
        event_type="goal_completion_toggled",
        details={"goal_id": goal.id, "is_completed": goal.is_completed},
        level="info",
        user_id=current_user.id
    )
    
    return goal 