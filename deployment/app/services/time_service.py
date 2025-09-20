"""
Time service for handling timezone-aware operations and date management.
"""

from datetime import datetime, date, time
from typing import Optional
import pytz
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.db.models import User

class TimeService:
    """Service for managing time and timezone operations"""
    
    @staticmethod
    def get_user_timezone(user: User) -> pytz.BaseTzInfo:
        """Get user's timezone object"""
        try:
            return pytz.timezone(user.timezone)
        except Exception:
            # Default to UTC if timezone is invalid
            return pytz.UTC
    
    @staticmethod
    def get_base_utc_time(user: User) -> datetime:
        """
        Get the base UTC time - either real current time or mock time if enabled.
        This is the core method that determines whether to use real or mock time.
        """
        # Check if mock date is enabled and mock datetime is set
        if (hasattr(user, 'mock_date_enabled') and user.mock_date_enabled and 
            hasattr(user, 'mock_datetime_override') and user.mock_datetime_override is not None):
            
            # Use mock datetime as base UTC time
            mock_dt = user.mock_datetime_override
            
            # Ensure it's timezone-aware (should be stored as UTC)
            if mock_dt.tzinfo is None:
                mock_dt = pytz.UTC.localize(mock_dt)
            
            return mock_dt
        
        # Use real current UTC time
        return datetime.now(pytz.UTC)
    
    @staticmethod 
    def get_current_date_for_user(user: User) -> date:
        """Get current date in user's timezone (respects mock datetime if enabled)"""
        user_tz = TimeService.get_user_timezone(user)
        
        # Get base UTC time (real or mock)
        utc_now = TimeService.get_base_utc_time(user)
        
        # Convert to user's timezone
        user_now = utc_now.astimezone(user_tz)
        
        # Return date in user's timezone
        return user_now.date()
    
    @staticmethod 
    def get_user_current_date(user: User) -> date:
        """Alias for get_current_date_for_user - Get current date in user's timezone"""
        return TimeService.get_current_date_for_user(user)
    
    @staticmethod
    def get_current_time_for_user(user: User) -> datetime:
        """Get current datetime in user's timezone (respects mock datetime if enabled)"""
        user_tz = TimeService.get_user_timezone(user)
        
        # Get base UTC time (real or mock)
        utc_now = TimeService.get_base_utc_time(user)
        
        # Convert to user's timezone
        user_now = utc_now.astimezone(user_tz)
        
        return user_now
    
    @staticmethod
    def convert_to_user_timezone(dt: datetime, user: User) -> datetime:
        """Convert a datetime to user's timezone"""
        user_tz = TimeService.get_user_timezone(user)
        
        # If datetime is naive, assume UTC
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        
        return dt.astimezone(user_tz)
    
    @staticmethod
    def start_of_day_user_tz(user: User, target_date: Optional[date] = None) -> datetime:
        """Get start of day (00:00:00) in user's timezone for target date"""
        user_tz = TimeService.get_user_timezone(user)
        
        if target_date is None:
            target_date = TimeService.get_current_date_for_user(user)
        
        # Create start of day in user's timezone
        start_of_day = user_tz.localize(datetime.combine(target_date, time.min))
        
        return start_of_day
    
    @staticmethod
    def end_of_day_user_tz(user: User, target_date: Optional[date] = None) -> datetime:
        """Get end of day (23:59:59.999999) in user's timezone for target date"""
        user_tz = TimeService.get_user_timezone(user)
        
        if target_date is None:
            target_date = TimeService.get_current_date_for_user(user)
        
        # Create end of day in user's timezone
        end_of_day = user_tz.localize(datetime.combine(target_date, time.max))
        
        return end_of_day
    
    @staticmethod
    def date_range_user_tz(user: User, start_date: date, end_date: date):
        """Generate date range in user's timezone"""
        current_date = start_date
        while current_date <= end_date:
            yield current_date
            # Move to next day
            from datetime import timedelta
            current_date += timedelta(days=1)
    
    @staticmethod
    def parse_date_string(date_str: str) -> date:
        """Parse date string in YYYY-MM-DD format"""
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    
    @staticmethod
    def format_date(date_obj: date) -> str:
        """Format date as YYYY-MM-DD string"""
        return date_obj.strftime("%Y-%m-%d")
    
    @staticmethod
    def get_week_start(target_date: date, user: User) -> date:
        """Get the start of the week (Monday) for the given date"""
        days_since_monday = target_date.weekday()
        from datetime import timedelta
        return target_date - timedelta(days=days_since_monday)
    
    @staticmethod
    def get_month_start(target_date: date) -> date:
        """Get the start of the month for the given date"""
        return target_date.replace(day=1)
    
    @staticmethod
    def get_month_end(target_date: date) -> date:
        """Get the end of the month for the given date"""
        from calendar import monthrange
        _, last_day = monthrange(target_date.year, target_date.month)
        return target_date.replace(day=last_day)
    
    @staticmethod
    def is_mock_enabled(user: User) -> bool:
        """Check if mock datetime is enabled for the user"""
        return (hasattr(user, 'mock_date_enabled') and user.mock_date_enabled and 
                hasattr(user, 'mock_datetime_override') and user.mock_datetime_override is not None)
    
    @staticmethod
    def get_detailed_time_info(user: User) -> dict:
        """Get detailed time information for the user matching frontend expectations"""
        # Get current time in user's timezone
        user_datetime = TimeService.get_current_time_for_user(user)
        user_date = user_datetime.date()
        
        # Get current UTC time (base time that respects mock settings)
        utc_datetime = TimeService.get_base_utc_time(user)
        
        # Calculate additional time information
        day_of_week = user_datetime.strftime("%A")
        week_number = user_datetime.isocalendar()[1]
        is_weekend = user_datetime.weekday() >= 5  # Saturday = 5, Sunday = 6
        
        # Calculate day boundaries in UTC for the user's current date
        start_of_day_user_tz = TimeService.start_of_day_user_tz(user, user_date)
        end_of_day_user_tz = TimeService.end_of_day_user_tz(user, user_date)
        
        # Convert day boundaries to UTC
        start_utc = start_of_day_user_tz.astimezone(pytz.UTC)
        end_utc = end_of_day_user_tz.astimezone(pytz.UTC)
        
        # Mock date status
        is_mock_date = TimeService.is_mock_enabled(user)
        
        return {
            # Required primary fields (frontend expectations)
            "user_date": user_date.strftime("%Y-%m-%d"),
            "user_datetime": user_datetime.isoformat(),
            "timezone": user.timezone,
            "utc_datetime": utc_datetime.isoformat(),
            "is_mock_date": is_mock_date,
            
            # Additional time context
            "day_of_week": day_of_week,
            "week_number": week_number,
            "is_weekend": is_weekend,
            "day_boundaries": {
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat()
            }
        } 