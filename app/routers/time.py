"""
Time Management Router

This router handles timezone-aware time operations including:
- Current time in user's timezone
- Date formatting and validation
- Timezone information for users

All operations respect user timezone settings for accurate time display.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.db.models import User
from app.services.time_service import TimeService
from app.core.config import settings

router = APIRouter()

# Response models for clear API documentation
class TimeResponse(BaseModel):
    """Time information response"""
    current_date: str = Field(..., description="Current date in YYYY-MM-DD format")
    current_time: str = Field(..., description="Current time in ISO format") 
    timezone: str = Field(..., description="User's timezone")
    utc_offset: str = Field(..., description="UTC offset (e.g., '-05:00')")

class TimezoneUpdateRequest(BaseModel):
    """Request to update user timezone"""
    timezone: str = Field(..., description="Valid timezone name (e.g., 'America/New_York')")

@router.get(
    "/current",
    response_model=TimeResponse,
    summary="Get Current Time",
    description="""
    Get the current date and time in the user's timezone.
    
    Returns:
    - Current date (YYYY-MM-DD)
    - Current time (ISO format)
    - User's timezone
    - UTC offset
    
    All times are returned in the user's configured timezone.
    """
)
async def get_current_time(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Get current time in user's timezone"""
    try:
        # Get current time in user's timezone
        current_time = TimeService.get_current_time_for_user(current_user)
        current_date = TimeService.get_current_date_for_user(current_user)
        
        # Format UTC offset
        utc_offset = current_time.strftime("%z")
        if utc_offset:
            # Format as +05:00 or -05:00
            utc_offset = f"{utc_offset[:3]}:{utc_offset[3:]}"
        else:
            utc_offset = "+00:00"
        
        return TimeResponse(
            current_date=current_date.strftime("%Y-%m-%d"),
            current_time=current_time.isoformat(),
            timezone=current_user.timezone,
            utc_offset=utc_offset
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting current time: {str(e)}")

@router.put(
    "/timezone",
    summary="Update User Timezone", 
    description="Update the user's timezone setting"
)
async def update_timezone(
    timezone_request: TimezoneUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update user's timezone"""
    try:
        # Validate timezone
        import pytz
        try:
            pytz.timezone(timezone_request.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            raise HTTPException(status_code=400, detail="Invalid timezone")
        
        # Update user's timezone
        current_user.timezone = timezone_request.timezone
        
        # Get updated current time
        current_time = TimeService.get_current_time_for_user(current_user)
        current_date = TimeService.get_current_date_for_user(current_user)
        
        return {
            "message": "Timezone updated successfully",
            "timezone": timezone_request.timezone,
            "current_date": current_date.strftime("%Y-%m-%d"),
            "current_time": current_time.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating timezone: {str(e)}")

@router.get(
    "/timezones",
    summary="List Available Timezones",
    description="Get a list of common timezones organized by region"
)
async def get_timezones():
    """Get list of available timezones"""
    try:
        import pytz
        
        # Common timezone groups
        common_timezones = {
            "America": [
                "America/New_York",
                "America/Chicago", 
                "America/Denver",
                "America/Los_Angeles",
                "America/Toronto",
                "America/Vancouver",
                "America/Mexico_City",
                "America/Sao_Paulo",
                "America/Argentina/Buenos_Aires"
            ],
            "Europe": [
                "Europe/London",
                "Europe/Paris",
                "Europe/Berlin",
                "Europe/Rome", 
                "Europe/Madrid",
                "Europe/Amsterdam",
                "Europe/Stockholm",
                "Europe/Moscow"
            ],
            "Asia": [
                "Asia/Tokyo",
                "Asia/Shanghai",
                "Asia/Hong_Kong",
                "Asia/Singapore",
                "Asia/Dubai",
                "Asia/Kolkata",
                "Asia/Seoul",
                "Asia/Jakarta"
            ],
            "Pacific": [
                "Pacific/Auckland",
                "Pacific/Sydney",
                "Pacific/Melbourne",
                "Pacific/Fiji",
                "Pacific/Honolulu"
            ],
            "Africa": [
                "Africa/Cairo",
                "Africa/Lagos",
                "Africa/Johannesburg",
                "Africa/Casablanca"
            ]
        }
        
        return {"timezones": common_timezones}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting timezones: {str(e)}")

@router.get(
    "/validate-date/{date_str}",
    summary="Validate Date Format",
    description="Validate if a date string is in the correct YYYY-MM-DD format"
)
async def validate_date(date_str: str):
    """Validate date format"""
    try:
        parsed_date = TimeService.parse_date_string(date_str)
        return {
            "valid": True,
            "date": parsed_date.strftime("%Y-%m-%d"),
            "day_of_week": parsed_date.strftime("%A"),
            "formatted": parsed_date.strftime("%B %d, %Y")
        }
    except ValueError as e:
        return {
            "valid": False,
            "error": str(e),
            "expected_format": "YYYY-MM-DD"
        } 