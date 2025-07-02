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
    def get_current_date_for_user(user: User) -> date:
        """Get current date in user's timezone"""
        user_tz = TimeService.get_user_timezone(user)
        
        # Get current UTC time
        utc_now = datetime.now(pytz.UTC)
        
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
        """Get current datetime in user's timezone"""
        user_tz = TimeService.get_user_timezone(user)
        
        # Get current UTC time  
        utc_now = datetime.now(pytz.UTC)
        
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