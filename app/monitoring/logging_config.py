"""
Production-ready structured logging configuration.
"""

import logging
import sys
import json
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import structlog
from pythonjsonlogger import jsonlogger

from app.core.config import settings


class CorrelationIDProcessor:
    """Add correlation ID to log records."""
    
    def __call__(self, logger, method_name, event_dict):
        # Get correlation ID from context or generate new one
        correlation_id = structlog.contextvars.get_contextvars().get('correlation_id')
        if correlation_id:
            event_dict['correlation_id'] = correlation_id
        return event_dict


class TimestampProcessor:
    """Add ISO timestamp to log records."""
    
    def __call__(self, logger, method_name, event_dict):
        event_dict['timestamp'] = datetime.utcnow().isoformat()
        return event_dict


class ProductionFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for production logs."""
    
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add standard fields
        log_record['timestamp'] = datetime.utcnow().isoformat()
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno
        
        # Add environment info
        log_record['environment'] = settings.APP_ENV
        log_record['service'] = settings.APP_NAME


def setup_structured_logging():
    """Configure structured logging for production."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            CorrelationIDProcessor(),
            TimestampProcessor(),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    if settings.is_production():
        # JSON formatting for production
        formatter = ProductionFormatter(
            '%(timestamp)s %(level)s %(logger)s %(correlation_id)s %(message)s'
        )
        
        # Set log level
        log_level = logging.INFO
    else:
        # Human-readable formatting for development
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        log_level = logging.DEBUG
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Add file handler for production
    if settings.is_production():
        file_handler = logging.FileHandler('/var/log/refocused/app.log')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    
    # Configure specific loggers
    
    # Silence noisy libraries
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    # Application loggers
    logging.getLogger('app').setLevel(log_level)
    logging.getLogger('security').setLevel(logging.INFO)
    logging.getLogger('auth').setLevel(logging.INFO)
    logging.getLogger('api').setLevel(logging.INFO)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Request logging utilities
def log_request_start(method: str, path: str, user_id: Optional[int] = None):
    """Log request start."""
    logger = get_logger("api.request")
    logger.info(
        "Request started",
        method=method,
        path=path,
        user_id=user_id
    )


def log_request_end(method: str, path: str, status_code: int, duration_ms: float, user_id: Optional[int] = None):
    """Log request completion."""
    logger = get_logger("api.request")
    logger.info(
        "Request completed",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        user_id=user_id
    )


def log_database_query(operation: str, table: str, duration_ms: float, rows_affected: Optional[int] = None):
    """Log database operations."""
    logger = get_logger("database")
    logger.debug(
        "Database query",
        operation=operation,
        table=table,
        duration_ms=duration_ms,
        rows_affected=rows_affected
    )


def log_security_event(event_type: str, user_id: Optional[int] = None, ip_address: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
    """Log security events."""
    logger = get_logger("security")
    logger.warning(
        "Security event",
        event_type=event_type,
        user_id=user_id,
        ip_address=ip_address,
        details=details or {}
    )


def log_business_event(event_type: str, user_id: int, details: Optional[Dict[str, Any]] = None):
    """Log business events for analytics."""
    logger = get_logger("business")
    logger.info(
        "Business event",
        event_type=event_type,
        user_id=user_id,
        details=details or {}
    ) 