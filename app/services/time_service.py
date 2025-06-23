"""
Global Time Management Service

This service handles all date/time operations for the ReFocused application,
ensuring consistent timezone handling for users worldwide.

Based on industry best practices from:
- Moesif API timezone guidelines
- Tinybird database timestamp practices 
- Leading habit tracker apps (Streaks, Habitica, Way of Life)
"""

from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, List, Tuple
import pytz
from pytz import timezone as pytz_timezone, UnknownTimeZoneError
import requests
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.models import User
import logging

logger = logging.getLogger(__name__)

# Valid IANA timezone identifiers (subset of most common ones)
COMMON_TIMEZONES = [
    "UTC", "America/New_York", "America/Los_Angeles", "America/Chicago", 
    "America/Denver", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Asia/Tokyo", "Asia/Shanghai", "Asia/Kolkata", "Australia/Sydney",
    "America/Toronto", "America/Vancouver", "Europe/Madrid", "Europe/Rome",
    "Asia/Seoul", "Asia/Hong_Kong", "America/Mexico_City", "America/Sao_Paulo"
]

class TimeService:
    """
    Centralized time management service following global best practices.
    
    Key principles:
    1. Store everything in UTC in database (Tinybird recommendation)
    2. Always use IANA timezone identifiers, never offsets (Moesif guideline)
    3. Be liberal in what you accept, conservative in what you send (Moesif)
    4. Default to UTC for unknown/invalid timezones
    5. Support user timezone detection and manual override
    """
    
    def __init__(self):
        self.utc = pytz.UTC
        
    def get_user_current_date(self, user: User) -> date:
        """
        Get current date in user's timezone.
        This is the primary function for habit tracking.
        
        Args:
            user: User object with timezone information
            
        Returns:
            date: Current date in user's local timezone
        """
        try:
            # Handle mock date system (for development/testing)
            if settings.MOCK_DATE_ENABLED and settings.is_development():
                # Check for runtime mock date override
                if hasattr(settings, '_runtime_mock_date') and settings._runtime_mock_date:
                    mock_date = settings._runtime_mock_date
                else:
                    mock_date = datetime.strptime(settings.MOCK_DATE, "%Y-%m-%d").date()
                
                # Convert mock date to user's timezone context
                # (Mock date represents what the user would see as "today")
                return mock_date
            
            # Production: use real time with user's timezone
            user_tz = self._get_user_timezone(user)
            utc_now = datetime.now(self.utc)
            user_now = utc_now.astimezone(user_tz)
            return user_now.date()
            
        except Exception as e:
            logger.error(f"Error getting user current date: {e}")
            # Fallback to UTC date
            return datetime.now(self.utc).date()
    
    def get_user_current_datetime(self, user: User) -> datetime:
        """
        Get current datetime in user's timezone.
        
        Args:
            user: User object with timezone information
            
        Returns:
            datetime: Current datetime in user's timezone
        """
        try:
            # Handle mock date system
            if settings.MOCK_DATE_ENABLED and settings.is_development():
                if hasattr(settings, '_runtime_mock_date') and settings._runtime_mock_date:
                    mock_date = settings._runtime_mock_date
                else:
                    mock_date = datetime.strptime(settings.MOCK_DATE, "%Y-%m-%d").date()
                
                # Create datetime with current time but mock date
                user_tz = self._get_user_timezone(user)
                now_time = datetime.now(user_tz).time()
                return user_tz.localize(datetime.combine(mock_date, now_time))
            
            # Production: real time
            user_tz = self._get_user_timezone(user)
            utc_now = datetime.now(self.utc)
            return utc_now.astimezone(user_tz)
            
        except Exception as e:
            logger.error(f"Error getting user current datetime: {e}")
            return datetime.now(self.utc)
    
    def convert_to_user_timezone(self, utc_datetime: datetime, user: User) -> datetime:
        """
        Convert UTC datetime to user's local timezone.
        
        Args:
            utc_datetime: Datetime in UTC
            user: User object with timezone information
            
        Returns:
            datetime: Datetime in user's timezone
        """
        try:
            if utc_datetime.tzinfo is None:
                utc_datetime = self.utc.localize(utc_datetime)
            elif utc_datetime.tzinfo != self.utc:
                utc_datetime = utc_datetime.astimezone(self.utc)
            
            user_tz = self._get_user_timezone(user)
            return utc_datetime.astimezone(user_tz)
            
        except Exception as e:
            logger.error(f"Error converting to user timezone: {e}")
            return utc_datetime
    
    def convert_to_utc(self, local_datetime: datetime, user: User) -> datetime:
        """
        Convert user's local datetime to UTC for database storage.
        
        Args:
            local_datetime: Datetime in user's timezone
            user: User object with timezone information
            
        Returns:
            datetime: Datetime in UTC
        """
        try:
            user_tz = self._get_user_timezone(user)
            
            if local_datetime.tzinfo is None:
                local_datetime = user_tz.localize(local_datetime)
            
            return local_datetime.astimezone(self.utc)
            
        except Exception as e:
            logger.error(f"Error converting to UTC: {e}")
            return local_datetime if local_datetime.tzinfo else self.utc.localize(local_datetime)
    
    def is_same_day_for_user(self, date1: date, date2: date, user: User) -> bool:
        """
        Check if two dates are the same day in user's timezone.
        Critical for habit streak calculations.
        
        Args:
            date1: First date
            date2: Second date  
            user: User object with timezone information
            
        Returns:
            bool: True if same day in user's timezone
        """
        try:
            # Convert dates to user's timezone context
            user_tz = self._get_user_timezone(user)
            
            # Create datetime objects at start of day in user's timezone
            dt1 = user_tz.localize(datetime.combine(date1, time.min))
            dt2 = user_tz.localize(datetime.combine(date2, time.min))
            
            return dt1.date() == dt2.date()
            
        except Exception as e:
            logger.error(f"Error comparing dates for user: {e}")
            return date1 == date2
    
    def get_start_of_day(self, target_date: date, user: User) -> datetime:
        """
        Get start of day (00:00:00) in user's timezone, returned as UTC.
        Used for habit completion queries.
        
        Args:
            target_date: Date to get start of day for
            user: User object with timezone information
            
        Returns:
            datetime: Start of day in UTC
        """
        try:
            user_tz = self._get_user_timezone(user)
            start_of_day = user_tz.localize(datetime.combine(target_date, time.min))
            return start_of_day.astimezone(self.utc)
            
        except Exception as e:
            logger.error(f"Error getting start of day: {e}")
            return self.utc.localize(datetime.combine(target_date, time.min))
    
    def get_end_of_day(self, target_date: date, user: User) -> datetime:
        """
        Get end of day (23:59:59.999999) in user's timezone, returned as UTC.
        Used for habit completion queries.
        
        Args:
            target_date: Date to get end of day for
            user: User object with timezone information
            
        Returns:
            datetime: End of day in UTC
        """
        try:
            user_tz = self._get_user_timezone(user)
            end_of_day = user_tz.localize(datetime.combine(target_date, time.max))
            return end_of_day.astimezone(self.utc)
            
        except Exception as e:
            logger.error(f"Error getting end of day: {e}")
            return self.utc.localize(datetime.combine(target_date, time.max))
    
    def detect_timezone_from_request(self, request) -> Tuple[str, str, float]:
        """
        Detect user's timezone from various request sources.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Tuple[str, str, float]: (timezone_id, detection_method, confidence)
        """
        # Try browser timezone from headers
        browser_tz = request.headers.get('X-Timezone')
        if browser_tz and self._is_valid_timezone(browser_tz):
            return browser_tz, "browser", 0.9
        
        # Try IP geolocation (lower confidence)
        try:
            client_ip = self._get_client_ip(request)
            if client_ip and not self._is_private_ip(client_ip):
                tz_from_ip = self._get_timezone_from_ip(client_ip)
                if tz_from_ip:
                    return tz_from_ip, "ip_geo", 0.6
        except Exception as e:
            logger.warning(f"IP geolocation failed: {e}")
        
        # Try Accept-Language header for country hints
        accept_lang = request.headers.get('Accept-Language', '')
        if accept_lang:
            tz_from_lang = self._get_timezone_from_language(accept_lang)
            if tz_from_lang:
                return tz_from_lang, "language", 0.4
        
        # Default fallback
        return "UTC", "default", 0.1
    
    def update_user_timezone(self, db: Session, user: User, timezone_id: str, 
                           method: str = "manual", confidence: float = 1.0) -> bool:
        """
        Update user's timezone with validation.
        
        Args:
            db: Database session
            user: User object to update
            timezone_id: IANA timezone identifier
            method: Detection method ('manual', 'auto', 'ip_geo')
            confidence: Confidence score (0.0-1.0)
            
        Returns:
            bool: True if successfully updated
        """
        try:
            if not self._is_valid_timezone(timezone_id):
                logger.warning(f"Invalid timezone: {timezone_id}")
                return False
            
            # Only update if confidence is higher than current
            if method != "manual" and confidence <= user.timezone_confidence:
                return False
            
            user.timezone = timezone_id
            user.timezone_detected_method = method
            user.timezone_confidence = confidence
            user.timezone_updated_at = datetime.now(self.utc)
            
            db.commit()
            logger.info(f"Updated user {user.id} timezone to {timezone_id} via {method}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating user timezone: {e}")
            db.rollback()
            return False
    
    def get_timezone_info(self, timezone_id: str) -> Dict[str, Any]:
        """
        Get comprehensive timezone information.
        
        Args:
            timezone_id: IANA timezone identifier
            
        Returns:
            Dict with timezone details
        """
        try:
            tz = pytz_timezone(timezone_id)
            now = datetime.now(tz)
            utc_now = datetime.now(self.utc)
            
            return {
                "timezone_id": timezone_id,
                "timezone_name": timezone_id,
                "current_time": now.isoformat(),
                "utc_offset": now.strftime("%z"),
                "utc_offset_seconds": int(now.utcoffset().total_seconds()),
                "is_dst": bool(now.dst()),
                "dst_name": now.tzname(),
                "country_code": self._get_country_from_timezone(timezone_id)
            }
            
        except Exception as e:
            logger.error(f"Error getting timezone info: {e}")
            return {
                "timezone_id": "UTC",
                "timezone_name": "UTC",
                "current_time": datetime.now(self.utc).isoformat(),
                "utc_offset": "+0000",
                "utc_offset_seconds": 0,
                "is_dst": False,
                "dst_name": "UTC",
                "country_code": None
            }
    
    def _get_user_timezone(self, user: User) -> pytz.BaseTzInfo:
        """Get user's timezone object, with fallback to UTC."""
        try:
            return pytz_timezone(user.timezone)
        except (UnknownTimeZoneError, AttributeError):
            logger.warning(f"Invalid timezone for user {user.id}: {getattr(user, 'timezone', 'None')}")
            return self.utc
    
    def _is_valid_timezone(self, timezone_id: str) -> bool:
        """Validate IANA timezone identifier."""
        try:
            pytz_timezone(timezone_id)
            return True
        except UnknownTimeZoneError:
            return False
    
    def _get_client_ip(self, request) -> Optional[str]:
        """Extract client IP from request headers."""
        # Check common proxy headers
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip
        
        return getattr(request.client, 'host', None)
    
    def _is_private_ip(self, ip: str) -> bool:
        """Check if IP is private/local."""
        private_ranges = ['127.', '192.168.', '10.', '172.']
        return any(ip.startswith(range_) for range_ in private_ranges)
    
    def _get_timezone_from_ip(self, ip: str) -> Optional[str]:
        """Get timezone from IP geolocation (placeholder - would use real service)."""
        # In production, use services like:
        # - ipapi.co
        # - ipinfo.io  
        # - MaxMind GeoIP2
        try:
            # Example implementation (would need API key)
            # response = requests.get(f"http://ip-api.com/json/{ip}")
            # data = response.json()
            # return data.get('timezone')
            pass
        except Exception:
            pass
        return None
    
    def _get_timezone_from_language(self, accept_language: str) -> Optional[str]:
        """Get timezone hint from Accept-Language header."""
        # Simple mapping of common language codes to timezones
        lang_to_tz = {
            'en-US': 'America/New_York',
            'en-GB': 'Europe/London',
            'fr-FR': 'Europe/Paris',
            'de-DE': 'Europe/Berlin',
            'ja-JP': 'Asia/Tokyo',
            'zh-CN': 'Asia/Shanghai',
            'es-ES': 'Europe/Madrid',
            'pt-BR': 'America/Sao_Paulo'
        }
        
        for lang in accept_language.split(','):
            lang_code = lang.split(';')[0].strip()
            if lang_code in lang_to_tz:
                return lang_to_tz[lang_code]
        
        return None
    
    def _get_country_from_timezone(self, timezone_id: str) -> Optional[str]:
        """Extract country code from timezone ID."""
        # Simple extraction from timezone name
        if '/' in timezone_id:
            continent_or_country = timezone_id.split('/')[0]
            continent_to_country = {
                'America': 'US',  # Simplified
                'Europe': 'EU',   # Simplified
                'Asia': 'AS',     # Simplified
                'Australia': 'AU',
                'Africa': 'AF'    # Simplified
            }
            return continent_to_country.get(continent_or_country)
        return None

# Global instance
time_service = TimeService() 