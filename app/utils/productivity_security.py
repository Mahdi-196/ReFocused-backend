from functools import wraps
from typing import Callable, Any
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import re
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ProductivitySecurityMiddleware:
    """Security middleware specifically for productivity endpoints."""
    
    ALLOWED_ACTIVITY_TYPES = [
        "pomodoro", "meditation", "breathing", "journal", 
        "gratitude", "habit", "goal"
    ]
    
    MAX_ACTIVITY_DATA_SIZE = 10 * 1024  # 10KB limit
    MAX_SESSION_ID_LENGTH = 100
    MAX_DEVICE_INFO_SIZE = 2 * 1024  # 2KB limit
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|SCRIPT)\b)',
        r'(--|\#|\/\*|\*\/)',
        r'(\bOR\b.*\b=\b.*\bOR\b)',
        r'(\bAND\b.*\b=\b.*\bAND\b)',
        r'(\b1\b.*\b=\b.*\b1\b)',
        r'(\'\s*OR\s*\')',
        r'(\"\s*OR\s*\")',
        r'(\bxp_cmdshell\b)',
        r'(\bsp_\w+\b)',
        r'(\bSYSTEM\b)',
        r'(\bEXEC\b)',
        r'(\bEXECUTE\b)',
    ]
    
    # XSS patterns
    XSS_PATTERNS = [
        r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>',
        r'<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>',
        r'<object\b[^<]*(?:(?!<\/object>)<[^<]*)*<\/object>',
        r'<embed\b[^<]*(?:(?!<\/embed>)<[^<]*)*<\/embed>',
        r'<form\b[^<]*(?:(?!<\/form>)<[^<]*)*<\/form>',
        r'javascript:',
        r'vbscript:',
        r'on\w+\s*=',
        r'expression\s*\(',
        r'@import',
        r'eval\s*\(',
        r'setTimeout\s*\(',
        r'setInterval\s*\(',
    ]
    
    @staticmethod
    def validate_activity_data(activity_data: dict) -> None:
        """Validate activity data for security threats."""
        if not isinstance(activity_data, dict):
            raise HTTPException(status_code=400, detail="Activity data must be a dictionary")
        
        # Check size
        data_str = json.dumps(activity_data)
        if len(data_str) > ProductivitySecurityMiddleware.MAX_ACTIVITY_DATA_SIZE:
            raise HTTPException(status_code=400, detail="Activity data too large")
        
        # Check for SQL injection and XSS
        ProductivitySecurityMiddleware._check_malicious_content(data_str)
        
        # Validate specific fields
        for key, value in activity_data.items():
            if isinstance(value, str):
                ProductivitySecurityMiddleware._validate_string_field(key, value)
            elif isinstance(value, (int, float)):
                ProductivitySecurityMiddleware._validate_numeric_field(key, value)
    
    @staticmethod
    def validate_session_id(session_id: str) -> str:
        """Validate and sanitize session ID."""
        if not session_id:
            return session_id
        
        if len(session_id) > ProductivitySecurityMiddleware.MAX_SESSION_ID_LENGTH:
            raise HTTPException(status_code=400, detail="Session ID too long")
        
        # Check for malicious content
        ProductivitySecurityMiddleware._check_malicious_content(session_id)
        
        # Sanitize - only allow alphanumeric, hyphens, and underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', session_id)
        if not sanitized:
            raise HTTPException(status_code=400, detail="Invalid session ID format")
        
        return sanitized
    
    @staticmethod
    def validate_device_info(device_info: dict) -> None:
        """Validate device information."""
        if not isinstance(device_info, dict):
            raise HTTPException(status_code=400, detail="Device info must be a dictionary")
        
        # Check size
        data_str = json.dumps(device_info)
        if len(data_str) > ProductivitySecurityMiddleware.MAX_DEVICE_INFO_SIZE:
            raise HTTPException(status_code=400, detail="Device info too large")
        
        # Check for malicious content
        ProductivitySecurityMiddleware._check_malicious_content(data_str)
        
        # Validate allowed keys
        allowed_keys = {
            'platform', 'version', 'user_agent', 'screen_resolution',
            'timezone', 'language', 'browser', 'os'
        }
        for key in device_info.keys():
            if key not in allowed_keys:
                raise HTTPException(status_code=400, detail=f"Invalid device info key: {key}")
    
    @staticmethod
    def validate_activity_type(activity_type: str) -> None:
        """Validate activity type."""
        if activity_type not in ProductivitySecurityMiddleware.ALLOWED_ACTIVITY_TYPES:
            raise HTTPException(status_code=400, detail="Invalid activity type")
    
    @staticmethod
    def validate_date_range(year: int, month: int) -> None:
        """Validate date range parameters."""
        current_year = datetime.now().year
        
        if not (2024 <= year <= current_year + 1):
            raise HTTPException(status_code=400, detail="Invalid year")
        
        if not (1 <= month <= 12):
            raise HTTPException(status_code=400, detail="Invalid month")
        
        # Don't allow future dates beyond next month
        future_limit = datetime.now() + timedelta(days=32)
        if year > future_limit.year or (year == future_limit.year and month > future_limit.month):
            raise HTTPException(status_code=400, detail="Date too far in the future")
    
    @staticmethod
    def _check_malicious_content(content: str) -> None:
        """Check for SQL injection and XSS patterns."""
        content_lower = content.lower()
        
        # Check SQL injection patterns
        for pattern in ProductivitySecurityMiddleware.SQL_INJECTION_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                logger.warning(f"SQL injection attempt detected: {pattern}")
                raise HTTPException(status_code=400, detail="Invalid input detected")
        
        # Check XSS patterns
        for pattern in ProductivitySecurityMiddleware.XSS_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                logger.warning(f"XSS attempt detected: {pattern}")
                raise HTTPException(status_code=400, detail="Invalid input detected")
    
    @staticmethod
    def _validate_string_field(key: str, value: str) -> None:
        """Validate string fields."""
        if not isinstance(value, str):
            return
        
        # Check length limits
        max_lengths = {
            'meditation_type': 50,
            'exercise_type': 50,
            'goal_type': 50,
            'completion_time': 30
        }
        
        max_length = max_lengths.get(key, 500)  # Default max length
        if len(value) > max_length:
            raise HTTPException(status_code=400, detail=f"Field '{key}' too long")
        
        # Check for malicious content
        ProductivitySecurityMiddleware._check_malicious_content(value)
    
    @staticmethod
    def _validate_numeric_field(key: str, value: (int, float)) -> None:
        """Validate numeric fields."""
        if not isinstance(value, (int, float)):
            return
        
        # Check reasonable ranges
        ranges = {
            'duration_minutes': (1, 480),  # 1 minute to 8 hours
            'interruptions': (0, 100),
            'word_count': (0, 50000),
            'character_count': (0, 100000),
            'time_spent_minutes': (0, 480),
            'progress_percentage': (0, 100),
            'quality_score': (0, 10)
        }
        
        if key in ranges:
            min_val, max_val = ranges[key]
            if not (min_val <= value <= max_val):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Field '{key}' must be between {min_val} and {max_val}"
                )

def productivity_security_check(func: Callable) -> Callable:
    """Decorator for productivity endpoint security checks."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            # Extract request from kwargs
            request = None
            for arg in args:
                if hasattr(arg, 'activity_data'):
                    request = arg
                    break
            
            if request:
                # Validate activity data
                if hasattr(request, 'activity_data'):
                    ProductivitySecurityMiddleware.validate_activity_data(request.activity_data)
                
                # Validate session ID
                if hasattr(request, 'session_id') and request.session_id:
                    request.session_id = ProductivitySecurityMiddleware.validate_session_id(request.session_id)
                
                # Validate device info
                if hasattr(request, 'device_info') and request.device_info:
                    ProductivitySecurityMiddleware.validate_device_info(request.device_info)
                
                # Validate activity type
                if hasattr(request, 'activity_type'):
                    ProductivitySecurityMiddleware.validate_activity_type(request.activity_type)
            
            # Execute the original function
            return await func(*args, **kwargs)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Security check failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Security validation failed")
    
    return wrapper

def validate_productivity_input(
    activity_data: dict = None,
    session_id: str = None,
    device_info: dict = None,
    activity_type: str = None
) -> None:
    """Standalone function for validating productivity inputs."""
    
    if activity_data is not None:
        ProductivitySecurityMiddleware.validate_activity_data(activity_data)
    
    if session_id is not None:
        ProductivitySecurityMiddleware.validate_session_id(session_id)
    
    if device_info is not None:
        ProductivitySecurityMiddleware.validate_device_info(device_info)
    
    if activity_type is not None:
        ProductivitySecurityMiddleware.validate_activity_type(activity_type)

class SecurityAuditLog:
    """Audit logging for security events."""
    
    @staticmethod
    def log_security_event(
        event_type: str,
        user_id: int,
        details: dict,
        severity: str = "INFO"
    ) -> None:
        """Log security events for audit trail."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "details": details,
            "severity": severity
        }
        
        if severity == "WARNING":
            logger.warning(f"Security Event: {json.dumps(log_entry)}")
        elif severity == "ERROR":
            logger.error(f"Security Event: {json.dumps(log_entry)}")
        else:
            logger.info(f"Security Event: {json.dumps(log_entry)}")
    
    @staticmethod
    def log_suspicious_activity(
        user_id: int,
        activity_type: str,
        details: str,
        ip_address: str = None
    ) -> None:
        """Log suspicious activity."""
        SecurityAuditLog.log_security_event(
            event_type="SUSPICIOUS_ACTIVITY",
            user_id=user_id,
            details={
                "activity_type": activity_type,
                "details": details,
                "ip_address": ip_address
            },
            severity="WARNING"
        )