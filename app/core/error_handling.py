from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import logging
import traceback
from datetime import datetime

logger = logging.getLogger("error")

class AppError(Exception):
    """Base application error class."""
    
    def __init__(
        self, 
        message: str, 
        status_code: int = 500, 
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)

class NotFoundError(AppError):
    """Resource not found error."""
    
    def __init__(
        self, 
        message: str = "Resource not found", 
        error_code: str = "NOT_FOUND",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status.HTTP_404_NOT_FOUND, error_code, details)

class ValidationErrorItem:
    """Model for validation error items."""
    
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "field": self.field,
            "message": self.message
        }

class ErrorResponse:
    """Standardized error response model."""
    
    def __init__(
        self,
        message: str,
        status_code: int,
        error_code: str,
        path: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        details: Optional[Dict[str, Any]] = None,
        validation_errors: Optional[List[ValidationErrorItem]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.path = path
        self.timestamp = timestamp or datetime.utcnow()
        self.details = details or {}
        self.validation_errors = validation_errors or []
    
    def to_dict(self) -> Dict[str, Any]:
        response = {
            "error": {
                "message": self.message,
                "code": self.error_code,
                "status": self.status_code,
                "timestamp": self.timestamp.isoformat(),
            }
        }
        
        if self.path:
            response["error"]["path"] = self.path
        
        if self.details:
            response["error"]["details"] = self.details
        
        if self.validation_errors:
            response["error"]["validation_errors"] = [
                error.to_dict() for error in self.validation_errors
            ]
        
        return response

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handler for application errors."""
    logger.error(f"Application error: {exc.error_code} - {exc.message}")
    
    error_response = ErrorResponse(
        message=exc.message,
        status_code=exc.status_code,
        error_code=exc.error_code,
        path=str(request.url.path),
        details=exc.details
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.to_dict()
    )

async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler for request validation errors."""
    validation_errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        message = error["msg"]
        validation_errors.append(ValidationErrorItem(field, message))
    
    logger.warning(f"Validation error: {request.url.path} - {len(validation_errors)} errors")
    
    error_response = ErrorResponse(
        message="Validation error",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="VALIDATION_ERROR",
        path=str(request.url.path),
        validation_errors=validation_errors
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.to_dict()
    )

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handler for HTTP exceptions."""
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    
    error_response = ErrorResponse(
        message=str(exc.detail),
        status_code=exc.status_code,
        error_code=f"HTTP_{exc.status_code}",
        path=str(request.url.path)
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.to_dict(),
        headers=exc.headers or {}
    )

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler for generic exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    
    error_response = ErrorResponse(
        message="An internal server error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_ERROR",
        path=str(request.url.path),
        details={"type": exc.__class__.__name__}
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict()
    )

def register_exception_handlers(app):
    """Register all exception handlers with the app."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler) 