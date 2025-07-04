"""
Time Management Router

This router handles timezone-aware time operations including:
- Current time in user's timezone
- Date formatting and validation
- Timezone information for users

All operations respect user timezone settings for accurate time display.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from fastapi.responses import JSONResponse
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from dateutil import parser
import pytz

from app.core.auth import get_current_user
from app.db.models import User, SecurityLog
from app.services.time_service import TimeService
from app.core.config import settings
from app.db.database import get_db
from app.schemas.time import (
    SetMockDateTimeRequest, 
    TimeResponse, 
    SetMockDateTimeResponse, 
    ResetMockDateResponse
)

router = APIRouter()

# Admin/Developer authorization dependency
async def get_admin_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Verify that the current user has admin/superuser privileges for debug endpoints."""
    if not current_user.is_superuser:
        # Log unauthorized access attempt
        await SecurityLog.log_event(
            db=db,
            event_type="unauthorized_debug_access",
            ip_address="unknown",  # Could be enhanced to get real IP
            user_id=current_user.id,
            details=f"User {current_user.email} attempted to access debug endpoint without admin privileges"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required. This endpoint is only available to superusers."
        )
    
    # Additional environment check - disable in production
    if settings.is_production():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug endpoints are not available in production environment"
        )
    
    return current_user

class TimezoneUpdateRequest(BaseModel):
    """Request to update user timezone"""
    timezone: str = Field(..., description="Valid timezone name (e.g., 'America/New_York')")

@router.get(
    "/current",
    response_model=TimeResponse,
    summary="Get Current Time",
    description="""
    Get the current date and time in the user's timezone with enhanced time information.
    
    Returns detailed time information including:
    - Current date and time in user's timezone
    - Week number, day of week, quarter
    - Mock date status and information (if enabled)
    - Additional time context
    
    All times respect mock datetime settings when enabled for testing.
    """
)
async def get_current_time(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Get current time in user's timezone with enhanced information"""
    try:
        # Get detailed time information using the enhanced service method
        time_info = TimeService.get_detailed_time_info(current_user)
        
        return TimeResponse(**time_info)
        
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

# Debug endpoints for Time Travel testing feature
@router.post(
    "/debug/set-date",
    response_model=SetMockDateTimeResponse,
    summary="Set Mock DateTime (Debug Only)",
    description="""
    Set a specific mock date and time for testing purposes. This endpoint enables "Time Travel" functionality.
    
    **Security Notice:** 
    - Only available to users with admin/superuser privileges
    - Disabled in production environments
    - All usage is logged for security auditing
    
    When a mock datetime is set, all time-related operations for the user will be based on this mock time 
    instead of the real system time. This allows for comprehensive testing of time-dependent features.
    
    The datetime should be provided in ISO format (e.g., '2024-01-15T10:30:00Z' or '2024-01-15T10:30:00-05:00').
    """
)
async def set_mock_datetime(
    request_data: SetMockDateTimeRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """Set mock datetime for time travel testing (admin only)"""
    try:
        # Parse and validate the datetime
        mock_datetime = parser.isoparse(request_data.new_datetime)
        
        # Ensure it's timezone-aware (convert to UTC if needed)
        if mock_datetime.tzinfo is None:
            mock_datetime = pytz.UTC.localize(mock_datetime)
        else:
            mock_datetime = mock_datetime.astimezone(pytz.UTC)
        
        # Update user's mock datetime settings
        admin_user.mock_date_enabled = True
        admin_user.mock_datetime_override = mock_datetime
        
        # Commit the changes
        await db.commit()
        await db.refresh(admin_user)
        
        # Log the debug action for security auditing
        await SecurityLog.log_event(
            db=db,
            event_type="debug_mock_datetime_set",
            ip_address="unknown",  # Could be enhanced to get real IP
            user_id=admin_user.id,
            details=f"Admin user {admin_user.email} set mock datetime to {mock_datetime.isoformat()}"
        )
        
        # Get the mock time in user's timezone for response
        user_datetime = TimeService.get_current_time_for_user(admin_user)
        
        return SetMockDateTimeResponse(
            message=f"Mock datetime successfully set to {mock_datetime.isoformat()}",
            is_mock_date=True,
            mock_datetime_utc=mock_datetime.isoformat(),
            user_datetime=user_datetime.isoformat()
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Error setting mock datetime: {str(e)}")

@router.post(
    "/debug/reset-date",
    response_model=ResetMockDateResponse,
    summary="Reset Mock DateTime (Debug Only)",
    description="""
    Reset the mock datetime back to real system time.
    
    **Security Notice:**
    - Only available to users with admin/superuser privileges
    - Disabled in production environments
    - All usage is logged for security auditing
    
    After calling this endpoint, all time-related operations will use the real system time.
    """
)
async def reset_mock_datetime(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """Reset mock datetime back to real system time (admin only)"""
    try:
        # Reset mock datetime settings
        admin_user.mock_date_enabled = False
        admin_user.mock_datetime_override = None
        
        # Commit the changes
        await db.commit()
        await db.refresh(admin_user)
        
        # Log the debug action for security auditing
        await SecurityLog.log_event(
            db=db,
            event_type="debug_mock_datetime_reset",
            ip_address="unknown",  # Could be enhanced to get real IP
            user_id=admin_user.id,
            details=f"Admin user {admin_user.email} reset mock datetime to real time"
        )
        
        # Get the current real time for response
        current_datetime = TimeService.get_current_time_for_user(admin_user)
        
        return ResetMockDateResponse(
            message="Mock datetime reset successfully. Now using real system time.",
            is_mock_date=False,
            current_datetime=current_datetime.isoformat()
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error resetting mock datetime: {str(e)}")

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