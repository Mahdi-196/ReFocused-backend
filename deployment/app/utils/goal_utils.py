"""
Goal utility functions for handling duration-based logic.
"""
from datetime import datetime, timezone, time
from calendar import monthrange


def calculate_2week_expiration(created_at: datetime) -> datetime:
    """
    Calculate the expiration timestamp for a 2-week goal based on creation date.
    
    Rules:
    - Goal expires exactly 14 days (2 weeks) from creation date
    - Expires at end of day (23:59:59 UTC) on the 14th day after creation
    
    Args:
        created_at: The creation timestamp of the goal
        
    Returns:
        datetime: The expiration timestamp in UTC
    """
    # Ensure we're working with UTC
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elif created_at.tzinfo != timezone.utc:
        created_at = created_at.astimezone(timezone.utc)
    
    # Calculate expiration: 14 days from creation date
    from datetime import timedelta
    expires_date = created_at + timedelta(days=14)
    
    # Set to end of day (23:59:59.999999)
    expires_date = expires_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return expires_date


def is_goal_expired(expires_at: datetime, current_time: datetime = None) -> bool:
    """
    Check if a 2-week goal has expired.
    
    Args:
        expires_at: The expiration timestamp of the goal
        current_time: The current time to compare against (defaults to now)
        
    Returns:
        bool: True if the goal has expired, False otherwise
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)
    
    # Ensure both timestamps are in UTC
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    elif expires_at.tzinfo != timezone.utc:
        expires_at = expires_at.astimezone(timezone.utc)
    
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    elif current_time.tzinfo != timezone.utc:
        current_time = current_time.astimezone(timezone.utc)
    
    return current_time > expires_at 