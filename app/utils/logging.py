import logging
import json
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

class StructuredFormatter(logging.Formatter):
    """
    Custom log formatter that outputs logs in structured JSON format.
    
    This makes logs easier to parse, filter, and analyze with log management tools.
    """
    
    def __init__(self, include_traceback: bool = True):
        super().__init__()
        self.include_traceback = include_traceback
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if available
        if record.exc_info and self.include_traceback:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": "".join(traceback.format_exception(*record.exc_info))
            }
        
        # Add extra attributes
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            for key, value in record.extra_data.items():
                if key not in log_data:
                    log_data[key] = value
        
        return json.dumps(log_data)

class StructuredLogger:
    """
    Logger that provides structured logging with consistent context.
    
    This allows adding context (like user_id, request_id) to all log entries.
    """
    
    def __init__(self, name: str, context: Optional[Dict[str, Any]] = None):
        self.logger = logging.getLogger(name)
        self.context = context or {}
    
    def _log(self, level: int, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log with combined context and extra data."""
        extra_data = {**self.context}
        if extra:
            extra_data.update(extra)
        
        extra_record = {"extra_data": extra_data}
        self.logger.log(level, msg, extra=extra_record, **kwargs)
    
    def debug(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log debug message with context."""
        self._log(logging.DEBUG, msg, extra, **kwargs)
    
    def info(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log info message with context."""
        self._log(logging.INFO, msg, extra, **kwargs)
    
    def warning(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log warning message with context."""
        self._log(logging.WARNING, msg, extra, **kwargs)
    
    def error(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log error message with context."""
        self._log(logging.ERROR, msg, extra, **kwargs)
    
    def critical(self, msg: str, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log critical message with context."""
        self._log(logging.CRITICAL, msg, extra, **kwargs)
    
    def with_context(self, **context) -> "StructuredLogger":
        """Create a new logger with additional context."""
        new_context = {**self.context, **context}
        return StructuredLogger(self.logger.name, new_context)

def setup_logging(level: int = logging.INFO, structured: bool = True):
    """
    Setup application-wide logging.
    
    Args:
        level: Logging level
        structured: Whether to use structured JSON logging
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    
    # Add console handler
    handler = logging.StreamHandler(sys.stdout)
    
    if structured:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    
    root_logger.addHandler(handler)
    
    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

def get_logger(name: str, context: Optional[Dict[str, Any]] = None) -> StructuredLogger:
    """
    Get a structured logger with context.
    
    Args:
        name: Logger name
        context: Initial context for all log messages
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name, context) 