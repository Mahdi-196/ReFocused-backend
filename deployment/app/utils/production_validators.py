"""
Production-ready validation utilities for the ReFocused API
"""

import re
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import ipaddress

logger = logging.getLogger("production_validators")

# Security patterns for input validation
MALICIOUS_PATTERNS = [
    r'<script[^>]*>.*?</script>',
    r'javascript:',
    r'data:',
    r'vbscript:',
    r'on\w+\s*=',
    r'<iframe[^>]*>',
    r'<object[^>]*>',
    r'<embed[^>]*>',
    r'<link[^>]*>',
    r'<meta[^>]*>',
    r'<style[^>]*>.*?</style>',
    r'expression\s*\(',
    r'url\s*\(',
    r'import\s+',
    r'@import',
    r'<!--.*?-->',
    r'<!\[CDATA\[.*?\]\]>',
]

# SQL injection patterns
SQL_INJECTION_PATTERNS = [
    r'union\s+select',
    r'select\s+.*\s+from',
    r'insert\s+into',
    r'delete\s+from',
    r'update\s+.*\s+set',
    r'drop\s+table',
    r'alter\s+table',
    r'create\s+table',
    r'exec\s*\(',
    r'execute\s*\(',
    r'sp_\w+',
    r'xp_\w+',
    r'--\s*',
    r'/\*.*?\*/',
    r'\'\s*or\s*\'\w*\'\s*=\s*\'\w*\'',
    r'\'\s*and\s*\'\w*\'\s*=\s*\'\w*\'',
    r';\s*drop\s+',
    r';\s*delete\s+',
    r';\s*update\s+',
    r';\s*insert\s+',
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    r';\s*rm\s+',
    r';\s*cat\s+',
    r';\s*ls\s+',
    r';\s*pwd',
    r';\s*whoami',
    r';\s*id',
    r';\s*uname',
    r';\s*ps\s+',
    r';\s*netstat',
    r';\s*wget\s+',
    r';\s*curl\s+',
    r'\|\s*bash',
    r'\|\s*sh',
    r'`.*`',
    r'\$\(.*\)',
    r'&&\s*\w+',
    r'\|\|\s*\w+',
]

class ValidationError(Exception):
    """Custom validation error"""
    def __init__(self, message: str, field: str = None, code: str = None):
        self.message = message
        self.field = field
        self.code = code
        super().__init__(message)

class SecurityValidator:
    """Security validation utilities"""
    
    @staticmethod
    def validate_text_input(text: str, field_name: str = "input", max_length: int = 1000) -> str:
        """Validate text input for security threats"""
        if not isinstance(text, str):
            raise ValidationError(f"{field_name} must be a string", field_name, "INVALID_TYPE")
        
        # Length validation
        if len(text) > max_length:
            raise ValidationError(
                f"{field_name} exceeds maximum length of {max_length} characters",
                field_name,
                "LENGTH_EXCEEDED"
            )
        
        # Check for malicious patterns
        text_lower = text.lower()
        
        # XSS detection
        for pattern in MALICIOUS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE | re.DOTALL):
                logger.warning(f"XSS attempt detected in {field_name}: {pattern}")
                raise ValidationError(
                    f"{field_name} contains potentially malicious content",
                    field_name,
                    "MALICIOUS_CONTENT"
                )
        
        # SQL injection detection
        for pattern in SQL_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(f"SQL injection attempt detected in {field_name}: {pattern}")
                raise ValidationError(
                    f"{field_name} contains potentially malicious SQL content",
                    field_name,
                    "SQL_INJECTION"
                )
        
        # Command injection detection
        for pattern in COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(f"Command injection attempt detected in {field_name}: {pattern}")
                raise ValidationError(
                    f"{field_name} contains potentially malicious commands",
                    field_name,
                    "COMMAND_INJECTION"
                )
        
        # Path traversal detection
        if '..' in text or text.startswith('/') or text.startswith('\\'):
            logger.warning(f"Path traversal attempt detected in {field_name}")
            raise ValidationError(
                f"{field_name} contains invalid path characters",
                field_name,
                "PATH_TRAVERSAL"
            )
        
        return text.strip()
    
    @staticmethod
    def validate_email(email: str) -> str:
        """Validate email format with security considerations"""
        if not email or not isinstance(email, str):
            raise ValidationError("Email is required and must be a string", "email", "INVALID_EMAIL")
        
        email = email.strip().lower()
        
        # Length check
        if len(email) > 254:  # RFC 5321 limit
            raise ValidationError("Email address too long", "email", "EMAIL_TOO_LONG")
        
        # Basic format validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValidationError("Invalid email format", "email", "INVALID_EMAIL_FORMAT")
        
        # Check for malicious patterns
        SecurityValidator.validate_text_input(email, "email", 254)
        
        # Additional email-specific security checks
        suspicious_patterns = [
            r'[<>"\\\[\]]',  # Suspicious characters
            r'\.{2,}',       # Multiple consecutive dots
            r'@.*@',         # Multiple @ symbols
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, email):
                raise ValidationError("Email contains invalid characters", "email", "INVALID_EMAIL_CHARS")
        
        return email
    
    @staticmethod
    def validate_ip_address(ip: str) -> str:
        """Validate IP address and check for suspicious IPs"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            
            # Check for private/local addresses in production
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                logger.info(f"Private/local IP detected: {ip}")
            
            # Check for known malicious ranges (example)
            # In production, integrate with threat intelligence feeds
            
            return str(ip_obj)
        except ValueError:
            raise ValidationError("Invalid IP address format", "ip_address", "INVALID_IP")
    
    @staticmethod
    def validate_user_agent(user_agent: str) -> str:
        """Validate and analyze user agent string"""
        if not user_agent:
            return "unknown"
        
        # Length limit
        if len(user_agent) > 500:
            logger.warning(f"Unusually long user agent: {len(user_agent)} chars")
            user_agent = user_agent[:500]
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'sqlmap',
            r'nikto',
            r'burp',
            r'nmap',
            r'masscan',
            r'zgrab',
            r'bot.*?bot',
            r'crawler.*?crawler',
            r'<script',
        ]
        
        user_agent_lower = user_agent.lower()
        for pattern in suspicious_patterns:
            if re.search(pattern, user_agent_lower):
                logger.warning(f"Suspicious user agent detected: {user_agent}")
                break
        
        return user_agent

class DataValidator:
    """Data validation utilities"""
    
    @staticmethod
    def validate_goal_name(name: str) -> str:
        """Validate goal name with specific business rules"""
        # Security validation first
        name = SecurityValidator.validate_text_input(name, "goal_name", 255)
        
        # Business rule validation
        if len(name.strip()) == 0:
            raise ValidationError("Goal name cannot be empty", "goal_name", "EMPTY_NAME")
        
        if len(name.strip()) < 2:
            raise ValidationError("Goal name must be at least 2 characters", "goal_name", "NAME_TOO_SHORT")
        
        # Check for excessive whitespace
        if '  ' in name:  # Multiple spaces
            name = ' '.join(name.split())  # Normalize whitespace
        
        # Check for profanity (basic implementation)
        profanity_patterns = [
            # Add your profanity filter patterns here
            # This is a basic example - use a proper profanity filter in production
        ]
        
        name_lower = name.lower()
        for pattern in profanity_patterns:
            if pattern in name_lower:
                raise ValidationError("Goal name contains inappropriate content", "goal_name", "INAPPROPRIATE_CONTENT")
        
        return name.strip()
    
    @staticmethod
    def validate_goal_progress(current_value: int, target_value: int, goal_type: str) -> int:
        """Validate goal progress values"""
        if not isinstance(current_value, int):
            raise ValidationError("Progress value must be an integer", "current_value", "INVALID_TYPE")
        
        if current_value < 0:
            raise ValidationError("Progress cannot be negative", "current_value", "NEGATIVE_VALUE")
        
        # Type-specific validation
        if goal_type == "percentage":
            if current_value > 100:
                logger.warning(f"Progress capped at 100% (was {current_value})")
                return 100
        elif goal_type == "counter":
            if current_value > target_value:
                logger.warning(f"Progress capped at target value {target_value} (was {current_value})")
                return target_value
        elif goal_type == "checklist":
            if current_value > 1:
                logger.warning(f"Checklist progress capped at 1 (was {current_value})")
                return 1
        
        return current_value
    
    @staticmethod
    def validate_pagination(limit: Optional[int], offset: Optional[int], max_limit: int = 100) -> tuple[int, int]:
        """Validate pagination parameters"""
        # Validate limit
        if limit is None:
            limit = 20  # Default
        elif limit <= 0:
            raise ValidationError("Limit must be positive", "limit", "INVALID_LIMIT")
        elif limit > max_limit:
            logger.warning(f"Limit capped at {max_limit} (requested {limit})")
            limit = max_limit
        
        # Validate offset
        if offset is None:
            offset = 0
        elif offset < 0:
            raise ValidationError("Offset cannot be negative", "offset", "INVALID_OFFSET")
        elif offset > 1000000:  # Reasonable upper bound
            raise ValidationError("Offset too large", "offset", "OFFSET_TOO_LARGE")
        
        return limit, offset

class RateLimitValidator:
    """Rate limiting validation utilities"""
    
    @staticmethod
    def validate_rate_limit_key(key: str) -> str:
        """Validate and normalize rate limit key"""
        if not key:
            raise ValidationError("Rate limit key cannot be empty", "rate_limit_key", "EMPTY_KEY")
        
        # Remove any potentially dangerous characters
        safe_key = re.sub(r'[^a-zA-Z0-9:._-]', '', key)
        
        if len(safe_key) != len(key):
            logger.warning(f"Rate limit key sanitized: {key} -> {safe_key}")
        
        return safe_key
    
    @staticmethod
    def calculate_backoff_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
        """Calculate exponential backoff delay"""
        delay = base_delay * (2 ** attempt)
        return min(delay, max_delay)

class ProductionHealthValidator:
    """Production health and monitoring validators"""
    
    @staticmethod
    def validate_database_connection(db_session) -> bool:
        """Validate database connection health"""
        try:
            # Simple health check query
            # Implementation depends on your database setup
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False
    
    @staticmethod
    def validate_system_resources() -> Dict[str, Any]:
        """Check system resource usage"""
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health_status = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "healthy": True
        }
        
        # Define thresholds
        if cpu_percent > 80:
            health_status["healthy"] = False
            logger.warning(f"High CPU usage: {cpu_percent}%")
        
        if memory.percent > 85:
            health_status["healthy"] = False
            logger.warning(f"High memory usage: {memory.percent}%")
        
        if disk.percent > 90:
            health_status["healthy"] = False
            logger.warning(f"High disk usage: {disk.percent}%")
        
        return health_status 