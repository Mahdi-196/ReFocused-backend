from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp
from contextlib import asynccontextmanager
from typing import Optional
import logging
import traceback
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session

logger = logging.getLogger("transaction")

@asynccontextmanager
async def transaction(session: Optional[AsyncSession] = None):
    """
    A context manager for managing database transactions.
    
    Usage:
    ```
    async with transaction() as session:
        # Your database operations
    ```
    
    Or with an existing session:
    ```
    async with transaction(existing_session):
        # Your database operations
    ```
    """
    external_session = session is not None
    session = session or async_session()
    
    try:
        async with session.begin():
            yield session
        
        # No need to commit as the session.begin() context manager will do it
    except Exception as e:
        logger.error(f"Transaction error: {str(e)}")
        # No need to rollback as the session.begin() context manager will do it
        raise
    finally:
        if not external_session:
            await session.close()

class TransactionMiddleware(BaseHTTPMiddleware):
    """
    Middleware that wraps each request in a database transaction.
    
    This middleware will automatically create a session and attach it to the request state.
    If the request completes successfully, the transaction will be committed.
    If an exception occurs, the transaction will be rolled back.
    
    Routes can access the session via request.state.db
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip for non-mutating requests
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)
        
        # Skip for static files, docs, health checks
        if any(path in request.url.path for path in ["/static/", "/docs", "/redoc", "/openapi.json", "/health"]):
            return await call_next(request)
        
        async with transaction() as session:
            # Attach session to request state
            request.state.db = session
            
            try:
                # Process the request
                response = await call_next(request)
                
                # Transaction is committed when exiting the context manager
                return response
            except Exception as e:
                logger.error(f"Request error in transaction: {str(e)}")
                logger.error(traceback.format_exc())
                # Transaction is rolled back when an exception occurs in the context manager
                raise 