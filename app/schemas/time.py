"""
Time-related Pydantic schemas for time management and debug endpoints.
"""

from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional
import pytz
from dateutil import parser


class SetMockDateTimeRequest(BaseModel):
    """Request schema for setting mock datetime for time travel testing."""
    new_datetime: str = Field(
        ..., 
        description="New datetime in ISO format (e.g., '2024-01-15T10:30:00Z' or '2024-01-15T10:30:00-05:00')"
    )
    
    @validator('new_datetime')
    def validate_datetime(cls, v):
        """Validate and parse datetime string."""
        try:
            # Parse datetime string using dateutil which handles various formats
            parsed_dt = parser.isoparse(v)
            
            # If timezone-naive, assume UTC
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=pytz.UTC)
            
            # Ensure it's not too far in the past or future (basic sanity check)
            now = datetime.now(pytz.UTC)
            if parsed_dt.year < 2020 or parsed_dt.year > now.year + 10:
                raise ValueError("Date must be between 2020 and 10 years from now")
                
            return v
        except Exception as e:
            raise ValueError(f"Invalid datetime format. Expected ISO format (e.g., '2024-01-15T10:30:00Z'). Error: {str(e)}")


class DayBoundaries(BaseModel):
    """Day boundaries in UTC for the user's date."""
    start_utc: str = Field(..., description="Start of day in UTC (ISO format)")
    end_utc: str = Field(..., description="End of day in UTC (ISO format)")


class TimeResponse(BaseModel):
    """Time information response matching frontend expectations."""
    # Required primary fields (in order of frontend preference)
    user_date: str = Field(..., description="Current date in user's timezone (YYYY-MM-DD format)")
    user_datetime: str = Field(..., description="Current datetime in user's timezone (ISO format)")
    timezone: str = Field(..., description="User's IANA timezone identifier")
    utc_datetime: str = Field(..., description="Current datetime in UTC (ISO format)")
    is_mock_date: bool = Field(..., description="Whether mock date/time is currently active")
    
    # Additional time context
    day_of_week: str = Field(..., description="Day of the week (e.g., 'Wednesday')")
    week_number: int = Field(..., description="ISO week number (1-53)")
    is_weekend: bool = Field(..., description="Whether current day is weekend (Saturday/Sunday)")
    day_boundaries: DayBoundaries = Field(..., description="Start and end of user's day in UTC")
    
    class Config:
        from_attributes = True


class ResetMockDateResponse(BaseModel):
    """Response schema for resetting mock date."""
    message: str = Field(..., description="Success message")
    is_mock_date: bool = Field(..., description="Mock date status after reset (should be False)")
    current_datetime: str = Field(..., description="Current real datetime after reset")
    
    class Config:
        from_attributes = True


class SetMockDateTimeResponse(BaseModel):
    """Response schema for setting mock datetime."""
    message: str = Field(..., description="Success message")
    is_mock_date: bool = Field(..., description="Mock date status (should be True)")
    mock_datetime_utc: str = Field(..., description="Mock datetime set in UTC (ISO format)")
    user_datetime: str = Field(..., description="Mock datetime in user's timezone (ISO format)")
    
    class Config:
        from_attributes = True 