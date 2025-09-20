import logging
import json
import datetime
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

def _resolve_security_log_path() -> str:
    """Return a writable log path, using /tmp on AWS Lambda."""
    configured_path = getattr(settings, "SECURITY_LOG_PATH", "security.log")
    running_on_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("AWS_EXECUTION_ENV"))
    if running_on_lambda:
        # Lambda filesystem is read-only except /tmp
        if not configured_path or not configured_path.startswith("/tmp"):
            return "/tmp/security.log"
    return configured_path or "security.log"


# Set up security logging
security_logger = logging.getLogger("app.security")
if not security_logger.handlers:
    try:
        log_handler = logging.FileHandler(_resolve_security_log_path())
    except Exception:
        # Fallback to stdout if file handler cannot be created
        log_handler = logging.StreamHandler()
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

def _get_signing_params() -> Dict[str, Any]:
    """Return key and algorithm for JWT signing based on settings."""
    alg = getattr(settings, "JWT_SIGNING_ALG", settings.ALGORITHM)
    if alg.upper() == "RS256" and settings.JWT_PRIVATE_KEY:
        return {"key": settings.JWT_PRIVATE_KEY, "algorithm": "RS256", "headers": {"kid": settings.JWT_KID} if settings.JWT_KID else {}}
    return {"key": settings.SECRET_KEY, "algorithm": "HS256", "headers": {}}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    
    # Add standard JWT claims
    iat = datetime.utcnow()
    if expires_delta:
        expire = iat + expires_delta
    else:
        expire = iat + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "iat": iat,  # Issued at
        "nbf": iat,  # Not valid before
        "exp": expire,  # Expiration
        "jti": f"access_{int(iat.timestamp())}_{hash(str(data))}",  # JWT ID
        "type": "access"  # Token type
    })
    signing = _get_signing_params()
    encoded_jwt = jwt.encode(to_encode, signing["key"], algorithm=signing["algorithm"], headers=signing["headers"])
    return encoded_jwt

def create_refresh_token(data: dict, expires_days: Optional[int] = None) -> str:
    to_encode = data.copy()
    
    # Add standard JWT claims
    iat = datetime.utcnow()
    days = expires_days or settings.REFRESH_TOKEN_EXPIRE_DAYS
    expire = iat + timedelta(days=days)
    
    to_encode.update({
        "iat": iat,  # Issued at
        "nbf": iat,  # Not valid before
        "exp": expire,  # Expiration
        "jti": f"refresh_{int(iat.timestamp())}_{hash(str(data))}",  # JWT ID
        "type": "refresh"  # Token type
    })
    signing = _get_signing_params()
    encoded_jwt = jwt.encode(to_encode, signing["key"], algorithm=signing["algorithm"], headers=signing["headers"])
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