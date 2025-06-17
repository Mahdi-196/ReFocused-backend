from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.database import get_db
from app.core.auth import get_current_active_user
from app.crud.statistics import StatisticsCRUD
from app.schemas.statistics import (
    FocusTimeUpdate,
    SessionsUpdate,
    TasksUpdate,
    StatisticsResponse,
    DetailedStatisticsResponse
)
from app.db.models import User

router = APIRouter()

@router.post("/focus", status_code=status.HTTP_200_OK)
async def update_focus_time(
    data: FocusTimeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update the user's daily focus time statistics.
    """
    await StatisticsCRUD.add_focus_time(db, current_user.id, data.seconds)
    return {"message": "Focus time updated successfully"}

@router.post("/sessions", status_code=status.HTTP_200_OK)
async def update_sessions(
    data: SessionsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update the user's daily completed sessions statistics.
    """
    await StatisticsCRUD.add_sessions(db, current_user.id, data.increment)
    return {"message": "Sessions updated successfully"}

@router.post("/tasks", status_code=status.HTTP_200_OK)
async def update_tasks(
    data: TasksUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update the user's daily completed tasks statistics.
    """
    await StatisticsCRUD.add_tasks(db, current_user.id, data.increment)
    return {"message": "Tasks updated successfully"}

@router.get("", response_model=StatisticsResponse)
async def get_statistics(
    filter: str = Query("D", description="Filter period: D (daily), W (weekly), M (monthly)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the user's statistics for the specified period.
    
    - D: Daily (today only)
    - W: Weekly (last 7 days)
    - M: Monthly (last 30 days)
    """
    # Validate filter
    if filter not in ["D", "W", "M"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filter value. Must be D, W, or M."
        )
        
    stats = await StatisticsCRUD.get_statistics(db, current_user.id, filter)
    
    return StatisticsResponse(
        focusTime=stats["focus_time"],
        sessions=stats["sessions"],
        tasksDone=stats["tasks_done"]
    )

@router.get("/detailed", response_model=DetailedStatisticsResponse)
async def get_detailed_statistics(
    filter: str = Query("D", description="Filter period: D (daily), W (weekly), M (monthly)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed statistics with daily breakdown for the specified period.
    """
    # Validate filter
    if filter not in ["D", "W", "M"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filter value. Must be D, W, or M."
        )
        
    result = await StatisticsCRUD.get_detailed_statistics(db, current_user.id, filter)
    
    summary = StatisticsResponse(
        focusTime=result["summary"]["focus_time"],
        sessions=result["summary"]["sessions"],
        tasksDone=result["summary"]["tasks_done"]
    )
    
    return DetailedStatisticsResponse(
        summary=summary,
        daily=result["daily"]
    ) 