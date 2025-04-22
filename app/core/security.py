import logging
import json
import datetime
from datetime import datetime, timedelta
from typing import Any, Union, Dict, Optional
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

def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# Security alert functions
def alert_suspicious_activity(user_id: Optional[int], activity_type: str, details: Dict[str, Any]):
    # Log suspicious stuff and maybe send an alert
    # TODO: Set up Slack webhook for alerts
    # TODO: Add rate limiting for alerts to avoid spam
    log_security_event(
        event_type="suspicious_activity",
        details={"activity_type": activity_type, **details},
        level="warning",
        user_id=user_id
    )
    
    # TODO: Add email alerts for critical stuff
    # TODO: Maybe add a dashboard for security events

def alert_authentication_failure(username: str, ip_address: str, reason: str):
    # Log failed login attempts
    # TODO: Add IP blocking after too many failures
    # TODO: Maybe add captcha after 3 failed attempts
    log_security_event(
        event_type="auth_failure",
        details={"username": username, "ip_address": ip_address, "reason": reason},
        level="warning"
    ) 