from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from app.db.database import get_db
from app.core.auth import get_current_active_user
from app.services.study_service import StudySetService
from app.db.models import User

# Session dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]

# Authentication dependency
CurrentUser = Annotated[User, Depends(get_current_active_user)]

def get_study_service(session: AsyncSession = Depends(get_db)) -> StudySetService:
    """
    Dependency for getting the study set service.
    
    Args:
        session: Database session
        
    Returns:
        StudySetService instance
    """
    return StudySetService(session)

# Create a reusable dependency with type annotation
StudyService = Annotated[StudySetService, Depends(get_study_service)]

def get_client_ip(request: Request) -> str:
    """
    Get client IP address from the request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Client IP address
    """
    # Try to get real IP from proxy headers
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Get the first IP in case of multiple proxies
        return forwarded_for.split(",")[0].strip()
    
    # Fall back to direct client IP
    return request.client.host if request.client else "unknown"

# Create a reusable dependency for client IP
ClientIP = Annotated[str, Depends(get_client_ip)]

# Optionally get transaction session from request state if using TransactionMiddleware
def get_request_session(request: Request, fallback: AsyncSession = Depends(get_db)) -> AsyncSession:
    """
    Get session from request state if available, otherwise use fallback.
    This is useful when using TransactionMiddleware.
    
    Args:
        request: FastAPI request object
        fallback: Fallback database session
        
    Returns:
        Database session
    """
    if hasattr(request.state, "db"):
        return request.state.db
    return fallback

# Create a reusable dependency for request session
RequestSession = Annotated[AsyncSession, Depends(get_request_session)] 