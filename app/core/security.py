import logging
import json
import datetime
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# Set up security logging
security_logger = logging.getLogger("app.security")
if not security_logger.handlers:
    # Configure handler if not already set up
    log_handler = logging.FileHandler("security.log")
    log_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    log_handler.setFormatter(log_formatter)
    security_logger.addHandler(log_handler)
    security_logger.setLevel(logging.INFO)

# Using bcrypt for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def log_security_event(event_type: str, details: Dict[str, Any], 
                      level: str = "info", user_id: Optional[int] = None):
    # Log security stuff to file
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "details": details
    }
    
    log_methods = {
        "debug": security_logger.debug,
        "info": security_logger.info,
        "warning": security_logger.warning,
        "error": security_logger.error,
        "critical": security_logger.critical
    }
    
    log_method = log_methods.get(level.lower(), security_logger.info)
    log_method(json.dumps(log_data))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "type": "access"
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# Security alert functions
def alert_suspicious_activity(user_id: Optional[int], activity_type: str, details: Dict[str, Any]):
    """Log suspicious activity for security monitoring."""
    log_security_event(
        event_type="suspicious_activity",
        details={"activity_type": activity_type, **details},
        level="warning",
        user_id=user_id
    )

def alert_authentication_failure(username: str, ip_address: str, reason: str):
    """Log failed authentication attempts for security monitoring."""
    log_security_event(
        event_type="auth_failure",
        details={"username": username, "ip_address": ip_address, "reason": reason},
        level="warning"
    ) 