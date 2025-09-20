import logging
import os
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import SecurityLog
from app.core.config import settings

# Configure security logger
logger = logging.getLogger("security")
logger.setLevel(logging.INFO)

if settings.SECURITY_LOG_ENABLED and not logger.handlers:
    log_path = getattr(settings, "SECURITY_LOG_PATH", "security.log") or "security.log"
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("AWS_EXECUTION_ENV"):
        if not os.path.isabs(log_path) or not log_path.startswith("/tmp"):
            log_path = "/tmp/security.log"
    try:
        handler = logging.FileHandler(log_path)
    except Exception:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(settings.SECURITY_LOG_FORMAT))
    logger.addHandler(handler)

async def log_security_event(
    db: AsyncSession,
    event_type: str,
    details: str,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """Log security events to both file and database."""
    try:
        # Log to file
        log_message = f"Security event: {event_type} - {details}"
        if user_id:
            log_message += f" (User ID: {user_id})"
        if ip_address:
            log_message += f" (IP: {ip_address})"
        logger.info(log_message)
        
        # Log to database
        log_entry = SecurityLog(
            event_type=event_type,
            details=details,
            user_id=user_id,
            ip_address=ip_address or "unknown",
            user_agent=user_agent
        )
        db.add(log_entry)
        await db.commit()
        
    except Exception as e:
        logger.error(f"Failed to log security event: {e}")

async def create_security_alert(
    db: AsyncSession,
    alert_type: str,
    severity: str,
    description: str,
    ip_address: Optional[str] = None,
    user_id: Optional[int] = None
) -> None:
    """Create a security alert."""
    try:
        from app.db.models import SecurityAlert
        
        alert = SecurityAlert(
            alert_type=alert_type,
            severity=severity,
            description=description,
            ip_address=ip_address,
            user_id=user_id,
            created_at=datetime.utcnow()
        )
        db.add(alert)
        await db.commit()
        
        # Log alert creation
        await log_security_event(
            db,
            "security_alert_created",
            f"New {severity} security alert: {description}",
            user_id,
            ip_address
        )
        
    except Exception as e:
        logger.error(f"Failed to create security alert: {e}") 