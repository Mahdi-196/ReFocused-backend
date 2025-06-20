from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime
import logging
import json

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

# Setup logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/focus", status_code=status.HTTP_200_OK)
async def update_focus_time(
    data: FocusTimeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update the user's daily focus time statistics in minutes.
    """
    try:
        logger.info(f"🔍 FOCUS data received: {data.model_dump()}")
        logger.info(f"Adding {data.minutes} minutes of focus time for user {current_user.id}")
        await StatisticsCRUD.add_focus_time(db, current_user.id, data.minutes)
        return {"message": "Focus time updated successfully"}
    except Exception as e:
        logger.error(f"Error updating focus time for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update focus time: {str(e)}"
        )

@router.post("/sessions", status_code=status.HTTP_200_OK)
async def update_sessions(
    data: SessionsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update the user's daily completed sessions statistics.
    """
    try:
        logger.info(f"🔍 SESSIONS data received: {data.model_dump()}")
        logger.info(f"Adding {data.increment} sessions for user {current_user.id}")
        await StatisticsCRUD.add_sessions(db, current_user.id, data.increment)
        return {"message": "Sessions updated successfully"}
    except Exception as e:
        logger.error(f"Error updating sessions for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update sessions: {str(e)}"
        )

@router.post("/tasks", status_code=status.HTTP_200_OK)
async def update_tasks(
    data: TasksUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update the user's daily completed tasks statistics.
    """
    try:
        logger.info(f"🔍 TASKS data received: {data.model_dump()}")
        logger.info(f"Adding {data.increment} tasks for user {current_user.id}")
        await StatisticsCRUD.add_tasks(db, current_user.id, data.increment)
        return {"message": "Tasks updated successfully"}
    except Exception as e:
        logger.error(f"Error updating tasks for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update tasks: {str(e)}"
        )

@router.get("", response_model=StatisticsResponse)
async def get_statistics(
    filter: str = Query("D", description="Filter period: D (daily), W (weekly), M (monthly)"),
    startDate: Optional[str] = Query(None, description="Start date for custom range (YYYY-MM-DD)"),
    endDate: Optional[str] = Query(None, description="End date for custom range (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the user's statistics for the specified period.
    
    - filter: D (daily), W (weekly), M (monthly) - used when startDate/endDate not provided
    - startDate/endDate: Custom date range (YYYY-MM-DD format)
    """
    try:
        # If custom date range is provided, use it instead of filter
        if startDate and endDate:
            # Validate date format
            try:
                start_date_obj = datetime.strptime(startDate, "%Y-%m-%d").date()
                end_date_obj = datetime.strptime(endDate, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
            
            logger.info(f"Getting custom range statistics for user {current_user.id}: {startDate} to {endDate}")
            stats = await StatisticsCRUD.get_statistics_by_date_range(db, current_user.id, start_date_obj, end_date_obj)
        else:
            # Validate filter
            if filter not in ["D", "W", "M"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid filter value. Must be D, W, or M."
                )
            
            logger.info(f"Getting {filter} statistics for user {current_user.id}")
            stats = await StatisticsCRUD.get_statistics(db, current_user.id, filter)
        
        response = StatisticsResponse(
            focusTime=stats["focus_time"],
            sessions=stats["sessions"],
            tasksDone=stats["tasks_done"]
        )
        logger.info(f"Returning stats for user {current_user.id}: {response.model_dump()}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting statistics for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )

@router.get("/detailed", response_model=DetailedStatisticsResponse)
async def get_detailed_statistics(
    filter: str = Query("D", description="Filter period: D (daily), W (weekly), M (monthly)"),
    startDate: Optional[str] = Query(None, description="Start date for custom range (YYYY-MM-DD)"),
    endDate: Optional[str] = Query(None, description="End date for custom range (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed statistics with daily breakdown for the specified period.
    """
    try:
        # If custom date range is provided, use it instead of filter
        if startDate and endDate:
            # Validate date format
            try:
                start_date_obj = datetime.strptime(startDate, "%Y-%m-%d").date()
                end_date_obj = datetime.strptime(endDate, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD"
                )
            
            logger.info(f"Getting detailed custom range statistics for user {current_user.id}: {startDate} to {endDate}")
            result = await StatisticsCRUD.get_detailed_statistics_by_date_range(db, current_user.id, start_date_obj, end_date_obj)
        else:
            # Validate filter
            if filter not in ["D", "W", "M"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid filter value. Must be D, W, or M."
                )
                
            logger.info(f"Getting detailed {filter} statistics for user {current_user.id}")
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting detailed statistics for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get detailed statistics: {str(e)}"
        )

@router.put("/{date}")
async def update_statistics_by_date(
    date: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update statistics for a specific date.
    Expected data format: {"focusTime": int (minutes), "sessions": int, "tasksDone": int}
    """
    try:
        # Validate date format
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD"
        )
    
    try:
        logger.info(f"Updating statistics for user {current_user.id} on {date}: {data}")
        
        # Update each statistic if provided
        if "focusTime" in data:
            await StatisticsCRUD.update_focus_time_for_date(
                db, current_user.id, date, data["focusTime"]
            )
        
        if "sessions" in data:
            await StatisticsCRUD.update_sessions_for_date(
                db, current_user.id, date, data["sessions"]
            )
        
        if "tasksDone" in data:
            await StatisticsCRUD.update_tasks_for_date(
                db, current_user.id, date, data["tasksDone"]
            )
        
        return {"message": f"Statistics updated successfully for {date}"}
        
    except Exception as e:
        logger.error(f"Error updating statistics for user {current_user.id} on {date}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update statistics for {date}: {str(e)}"
        )

@router.get("/debug/all")
async def debug_get_all_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Debug endpoint: Get all statistics records for the current user.
    This helps identify if data is being saved and what dates exist.
    """
    try:
        from sqlalchemy import select
        from app.db.models import UserStatistics
        
        result = await db.execute(
            select(UserStatistics).where(
                UserStatistics.user_id == current_user.id
            ).order_by(UserStatistics.date.desc())
        )
        
        all_stats = result.scalars().all()
        
        records = []
        for stat in all_stats:
            records.append({
                "id": stat.id,
                "date": stat.date.isoformat(),
                "focus_time_minutes": stat.focus_time_minutes,
                "completed_sessions": stat.completed_sessions,
                "completed_tasks": stat.completed_tasks,
                "created_at": stat.created_at.isoformat()
            })
        
        return {
            "user_id": current_user.id,
            "total_records": len(records),
            "records": records
        }
        
    except Exception as e:
        logger.error(f"Error getting debug statistics for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get debug statistics: {str(e)}"
        ) 