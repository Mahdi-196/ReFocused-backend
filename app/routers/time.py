"""
Global Time API Endpoints

Comprehensive date/time API following best practices from:
- Moesif API timezone guidelines  
- Tinybird database timestamp practices
- Leading habit tracker apps (Streaks, Habitica, Way of Life, etc.)

This is the SINGLE source of truth for all date/time operations
for both frontend and backend.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator

from app.core.database import get_db
from app.core.auth import get_current_user
from app.db.models import User
from app.services.time_service import time_service, COMMON_TIMEZONES
from app.core.config import settings

router = APIRouter(prefix="/time", tags=["time"])

# Pydantic models for request/response
class TimezoneCurrent(BaseModel):
    """Current time information for user's timezone."""
    # Server time (UTC) - always included for debugging
    server_utc: datetime = Field(..., description="Current server time in UTC (ISO 8601)")
    
    # User-specific time in their timezone  
    user_date: str = Field(..., description="Current date in user's timezone (YYYY-MM-DD)")
    user_time: str = Field(..., description="Current time in user's timezone (HH:MM:SS)")
    user_datetime: datetime = Field(..., description="Full datetime in user's timezone (ISO 8601)")
    
    # Timezone information
    timezone_id: str = Field(..., description="IANA timezone identifier (e.g., 'America/New_York')")
    timezone_name: str = Field(..., description="Human-readable timezone name")
    utc_offset: str = Field(..., description="UTC offset (e.g., '+0500', '-0800')")
    utc_offset_seconds: int = Field(..., description="UTC offset in seconds")
    is_dst: bool = Field(..., description="Whether daylight saving time is active")
    
    # System information for debugging
    is_mock_enabled: bool = Field(..., description="Whether mock date system is enabled")
    mock_date: Optional[str] = Field(None, description="Mock date if enabled")
    detection_method: str = Field(..., description="How timezone was detected")
    confidence: float = Field(..., description="Confidence in timezone detection (0.0-1.0)")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class TimezoneUpdate(BaseModel):
    """Request to update user's timezone."""
    timezone_id: str = Field(..., description="IANA timezone identifier")
    
    @validator('timezone_id')
    def validate_timezone(cls, v):
        if not time_service._is_valid_timezone(v):
            raise ValueError(f"Invalid timezone identifier: {v}")
        return v

class TimezoneDetection(BaseModel):
    """Timezone detection from browser/client."""
    detected_timezone: Optional[str] = Field(None, description="Browser-detected timezone")
    user_agent: Optional[str] = Field(None, description="Browser user agent")
    language: Optional[str] = Field(None, description="Browser language preference")

class BulkTimeInfo(BaseModel):
    """Bulk time information for date range."""
    dates: List[str] = Field(..., description="List of dates in user's timezone")
    start_times_utc: List[datetime] = Field(..., description="Start of day times in UTC")
    end_times_utc: List[datetime] = Field(..., description="End of day times in UTC")
    timezone_id: str = Field(..., description="User's timezone")

@router.get("/current", response_model=TimezoneCurrent)
async def get_current_time(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get current date and time (no authentication required).
    
    This is the PRIMARY endpoint that both frontend and backend should use
    for all date/time operations. It provides:
    
    - Current date and time in UTC or detected timezone
    - Comprehensive timezone information  
    - Mock date support for testing
    - Timezone detection metadata
    
    Returns everything in ISO 8601 format following REST API best practices.
    """
    try:
        # Auto-detect timezone from request
        detected_tz, method, confidence = time_service.detect_timezone_from_request(request)
        
        # Get all time information using the time service with detected timezone
        # Create a minimal user-like object for timezone info
        class SimpleTimezone:
            def __init__(self, tz):
                self.timezone = tz
        
        timezone_obj = SimpleTimezone(detected_tz)
        user_date = time_service.get_user_current_date(timezone_obj)
        user_datetime = time_service.get_user_current_datetime(timezone_obj)
        timezone_info = time_service.get_timezone_info(detected_tz)
        
        return TimezoneCurrent(
            server_utc=datetime.utcnow(),
            user_date=user_date.strftime("%Y-%m-%d"),
            user_time=user_datetime.strftime("%H:%M:%S"),
            user_datetime=user_datetime,
            timezone_id=detected_tz,
            timezone_name=timezone_info["timezone_name"],
            utc_offset=timezone_info["utc_offset"],
            utc_offset_seconds=timezone_info["utc_offset_seconds"],
            is_dst=timezone_info["is_dst"],
            is_mock_enabled=settings.MOCK_DATE_ENABLED and settings.is_development(),
            mock_date=settings.MOCK_DATE if settings.MOCK_DATE_ENABLED else None,
            detection_method=method,
            confidence=confidence
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting current time: {str(e)}")

@router.post("/timezone", response_model=Dict[str, Any])
async def update_timezone(
    timezone_update: TimezoneUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user's timezone manually.
    
    This endpoint allows users to override their timezone detection
    and set it manually. Has the highest confidence rating.
    """
    try:
        success = time_service.update_user_timezone(
            db, current_user, timezone_update.timezone_id, "manual", 1.0
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update timezone")
        
        # Return updated timezone info
        timezone_info = time_service.get_timezone_info(timezone_update.timezone_id)
        user_date = time_service.get_user_current_date(current_user)
        
        return {
            "message": "Timezone updated successfully",
            "timezone_id": timezone_update.timezone_id,
            "user_current_date": user_date.strftime("%Y-%m-%d"),
            "timezone_info": timezone_info
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating timezone: {str(e)}")

@router.post("/detect", response_model=Dict[str, Any])
async def detect_timezone(
    detection: TimezoneDetection,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Auto-detect user's timezone from browser/client information.
    
    This endpoint processes timezone detection from the frontend
    and updates the user's timezone if the detection confidence
    is higher than the current setting.
    """
    try:
        # Use provided timezone or detect from request
        if detection.detected_timezone and time_service._is_valid_timezone(detection.detected_timezone):
            detected_tz = detection.detected_timezone
            method = "browser"
            confidence = 0.9
        else:
            detected_tz, method, confidence = time_service.detect_timezone_from_request(request)
        
        # Update if better than current
        updated = False
        if confidence > current_user.timezone_confidence:
            updated = time_service.update_user_timezone(db, current_user, detected_tz, method, confidence)
        
        return {
            "detected_timezone": detected_tz,
            "detection_method": method,
            "confidence": confidence,
            "updated": updated,
            "current_timezone": current_user.timezone,
            "message": "Timezone detected" + (" and updated" if updated else " (not updated - current timezone has higher confidence)")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting timezone: {str(e)}")

@router.get("/timezones", response_model=List[Dict[str, Any]])
async def list_common_timezones():
    """
    Get list of common timezones for user selection.
    
    Returns the most commonly used IANA timezone identifiers
    with current offset and DST information.
    """
    try:
        timezones = []
        for tz_id in COMMON_TIMEZONES:
            info = time_service.get_timezone_info(tz_id)
            timezones.append({
                "timezone_id": tz_id,
                "timezone_name": tz_id,
                "display_name": tz_id.replace("_", " "),
                "utc_offset": info["utc_offset"],
                "is_dst": info["is_dst"],
                "country_code": info["country_code"]
            })
        
        # Sort by UTC offset for easier selection
        timezones.sort(key=lambda x: x["utc_offset"])
        return timezones
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing timezones: {str(e)}")

@router.get("/user-day-bounds", response_model=Dict[str, Any])
async def get_user_day_bounds(
    target_date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to user's current date)"),
    current_user: User = Depends(get_current_user)
):
    """
    Get start and end of day boundaries for habit tracking.
    
    This endpoint is critical for habit tracking queries - it returns
    the exact UTC timestamps that represent the start and end of a
    specific day in the user's timezone.
    
    Essential for:
    - Checking if habits were completed "today"
    - Querying database for date-specific records
    - Calculating streaks correctly across timezones
    """
    try:
        if target_date:
            try:
                parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        else:
            parsed_date = time_service.get_user_current_date(current_user)
        
        start_of_day_utc = time_service.get_start_of_day(parsed_date, current_user)
        end_of_day_utc = time_service.get_end_of_day(parsed_date, current_user)
        
        return {
            "target_date": parsed_date.strftime("%Y-%m-%d"),
            "timezone_id": current_user.timezone,
            "start_of_day_utc": start_of_day_utc.isoformat(),
            "end_of_day_utc": end_of_day_utc.isoformat(),
            "duration_hours": 24,
            "user_local_start": time_service.convert_to_user_timezone(start_of_day_utc, current_user).isoformat(),
            "user_local_end": time_service.convert_to_user_timezone(end_of_day_utc, current_user).isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating day bounds: {str(e)}")

@router.get("/week-info", response_model=Dict[str, Any])
async def get_week_info(
    target_date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to user's current date)"),
    current_user: User = Depends(get_current_user)
):
    """
    Get week information for habit tracking and analytics.
    
    Returns comprehensive week data including:
    - All dates in the week (user's timezone)
    - Day boundaries in UTC for database queries
    - Week start/end based on user's locale
    """
    try:
        from datetime import timedelta
        
        if target_date:
            try:
                parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        else:
            parsed_date = time_service.get_user_current_date(current_user)
        
        # Calculate week start (Monday)
        days_since_monday = parsed_date.weekday()
        week_start = parsed_date - timedelta(days=days_since_monday)
        
        # Generate week data
        week_dates = []
        week_bounds = []
        
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            start_utc = time_service.get_start_of_day(day_date, current_user)
            end_utc = time_service.get_end_of_day(day_date, current_user)
            
            week_dates.append(day_date.strftime("%Y-%m-%d"))
            week_bounds.append({
                "date": day_date.strftime("%Y-%m-%d"),
                "day_name": day_date.strftime("%A"),
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "is_today": day_date == time_service.get_user_current_date(current_user)
            })
        
        return {
            "target_date": parsed_date.strftime("%Y-%m-%d"),
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": (week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
            "timezone_id": current_user.timezone,
            "days": week_bounds,
            "week_dates": week_dates
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting week info: {str(e)}")

@router.get("/sync-check", response_model=Dict[str, Any])
async def sync_check(
    frontend_date: str = Query(..., description="Frontend's current date (YYYY-MM-DD)"),
    frontend_time: str = Query(..., description="Frontend's current time (HH:MM:SS)"),
    current_user: User = Depends(get_current_user)
):
    """
    Check if frontend and backend are synchronized.
    
    This endpoint helps detect clock drift, timezone mismatches,
    or other synchronization issues between frontend and backend.
    Critical for debugging time-related issues.
    """
    try:
        # Parse frontend values
        try:
            fe_date = datetime.strptime(frontend_date, "%Y-%m-%d").date()
            fe_time = datetime.strptime(frontend_time, "%H:%M:%S").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date/time format")
        
        # Get backend values
        be_date = time_service.get_user_current_date(current_user)
        be_datetime = time_service.get_user_current_datetime(current_user)
        be_time = be_datetime.time()
        
        # Calculate differences
        date_diff = (be_date - fe_date).days
        time_diff_seconds = (
            datetime.combine(date.today(), be_time) - 
            datetime.combine(date.today(), fe_time)
        ).total_seconds()
        
        # Determine sync status
        is_date_synced = abs(date_diff) <= 1  # Allow 1 day difference
        is_time_synced = abs(time_diff_seconds) <= 300  # Allow 5 minute difference
        is_synced = is_date_synced and is_time_synced
        
        return {
            "is_synced": is_synced,
            "frontend": {
                "date": frontend_date,
                "time": frontend_time
            },
            "backend": {
                "date": be_date.strftime("%Y-%m-%d"),
                "time": be_time.strftime("%H:%M:%S")
            },
            "differences": {
                "date_diff_days": date_diff,
                "time_diff_seconds": int(time_diff_seconds)
            },
            "timezone_id": current_user.timezone,
            "recommendations": self._get_sync_recommendations(date_diff, time_diff_seconds)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking sync: {str(e)}")

def _get_sync_recommendations(date_diff: int, time_diff_seconds: float) -> List[str]:
    """Get recommendations for sync issues."""
    recommendations = []
    
    if abs(date_diff) > 1:
        recommendations.append("Large date difference detected. Check timezone settings.")
    
    if abs(time_diff_seconds) > 300:
        recommendations.append("Time difference > 5 minutes. Check system clock.")
    
    if abs(time_diff_seconds) > 3600:
        recommendations.append("Time difference > 1 hour. Possible timezone mismatch.")
    
    if not recommendations:
        recommendations.append("Frontend and backend are well synchronized.")
    
    return recommendations

# Debug endpoint (development only)

@router.api_route("/debug/change-day", methods=["POST", "OPTIONS"], response_model=Dict[str, Any])
async def change_mock_date_by_day(
    request: Request,
    direction: int = Query(1, description="Change direction: +1 for next day, -1 for previous day")
):
    """
    🚧 TEMPORARY TESTING ENDPOINT 🚧
    
    Change the mock date by moving forward (+1) or backward (-1) by one day.
    This is only for testing habit streaks and date-dependent functionality.
    
    Parameters:
    - direction: +1 to move forward one day, -1 to move backward one day
    
    Returns the new mock date and system status.
    """
    # Handle OPTIONS preflight requests
    if request.method == "OPTIONS":
        return {}
    
    if not settings.is_development():
        raise HTTPException(status_code=403, detail="This endpoint is only available in development mode")
    
    if direction not in [1, -1]:
        raise HTTPException(status_code=400, detail="Direction must be +1 (forward) or -1 (backward)")
    
    try:
        from datetime import datetime, timedelta
        
        # Get current mock date or today's date
        current_mock = settings.get_current_date()
        
        # Calculate new date
        new_date = current_mock + timedelta(days=direction)
        
        # Update the mock date in settings
        settings.set_mock_date(new_date)
        settings.MOCK_DATE = new_date.strftime("%Y-%m-%d")
        settings.MOCK_DATE_ENABLED = True
        
        direction_text = "forward" if direction == 1 else "backward"
        
        return {
            "message": f"Mock date moved {direction_text} by 1 day",
            "previous_date": current_mock.strftime("%Y-%m-%d"),
            "new_date": new_date.strftime("%Y-%m-%d"),
            "direction": direction,
            "mock_enabled": True,
            "warning": "⚠️ TESTING MODE: This affects all date-dependent operations including habit streaks"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error changing mock date: {str(e)}")

@router.api_route("/debug/reset-date", methods=["POST", "OPTIONS"], response_model=Dict[str, Any])
async def reset_mock_date(request: Request):
    """
    🚧 TEMPORARY TESTING ENDPOINT 🚧
    
    Reset the mock date system to use real current date.
    This disables mock mode and returns to normal date operations.
    """
    # Handle OPTIONS preflight requests
    if request.method == "OPTIONS":
        return {}
    
    if not settings.is_development():
        raise HTTPException(status_code=403, detail="This endpoint is only available in development mode")
    
    try:
        from datetime import date
        
        # Clear the mock date
        settings.clear_mock_date()
        settings.MOCK_DATE_ENABLED = False
        
        real_date = date.today()
        
        return {
            "message": "Mock date system disabled - using real current date",
            "real_date": real_date.strftime("%Y-%m-%d"),
            "mock_enabled": False,
            "status": "✅ Back to normal date operations"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting mock date: {str(e)}")

@router.api_route("/debug/mock-date", methods=["POST", "OPTIONS"], response_model=Dict[str, Any])
async def set_mock_date_advanced(
    request: Request,
    mock_date: str = Query("", description="Mock date in YYYY-MM-DD format"),
    current_user: User = Depends(get_current_user)
):
    """
    Advanced mock date setting with timezone awareness.
    Development only - more sophisticated than the basic debug endpoint.
    """
    # Handle OPTIONS preflight requests
    if request.method == "OPTIONS":
        return {}
    
    if not settings.is_development():
        raise HTTPException(status_code=403, detail="Debug endpoints only available in development")
    
    if not mock_date:
        raise HTTPException(status_code=400, detail="mock_date parameter is required")
    
    try:
        parsed_date = datetime.strptime(mock_date, "%Y-%m-%d").date()
        settings.set_mock_date(parsed_date)
        
        # Get new current time with mock date
        user_date = time_service.get_user_current_date(current_user)
        user_datetime = time_service.get_user_current_datetime(current_user)
        
        return {
            "message": f"Mock date set to {mock_date}",
            "mock_date": mock_date,
            "user_timezone": current_user.timezone,
            "user_current_date": user_date.strftime("%Y-%m-%d"),
            "user_current_datetime": user_datetime.isoformat(),
            "server_utc": datetime.utcnow().isoformat()
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting mock date: {str(e)}") 