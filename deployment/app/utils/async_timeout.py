"""
Async timeout utilities to prevent Lambda functions from exceeding API Gateway limits.
"""
import asyncio
import functools
import logging
from typing import Any, Callable, Union
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def timeout_endpoint(timeout_seconds: int = 20):
    """
    Decorator to ensure endpoint functions complete within specified timeout.
    
    Args:
        timeout_seconds: Maximum time to allow function to run (default 20s)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            try:
                logger.info(f"Starting {func.__name__} with {timeout_seconds}s timeout")
                result = await asyncio.wait_for(
                    func(*args, **kwargs), 
                    timeout=timeout_seconds
                )
                logger.info(f"Completed {func.__name__} successfully")
                return result
                
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} exceeded {timeout_seconds}s timeout")
                raise HTTPException(
                    status_code=503,
                    detail=f"Request timed out after {timeout_seconds} seconds. Please try again."
                )
            except Exception as e:
                logger.error(f"{func.__name__} failed: {str(e)}")
                raise
                
        return async_wrapper
    return decorator

async def safe_db_operation(operation, timeout: int = 10, operation_name: str = "database operation"):
    """
    Safely execute database operations with timeout.
    
    Args:
        operation: Async operation to execute
        timeout: Timeout in seconds
        operation_name: Name for logging
    """
    try:
        logger.info(f"Starting {operation_name} with {timeout}s timeout")
        result = await asyncio.wait_for(operation, timeout=timeout)
        logger.info(f"Completed {operation_name} successfully")
        return result
    except asyncio.TimeoutError:
        logger.error(f"{operation_name} timed out after {timeout}s")
        raise HTTPException(
            status_code=503,
            detail=f"Database operation timed out. Please try again."
        )

async def safe_external_call(operation, timeout: int = 15, service_name: str = "external service"):
    """
    Safely execute external API calls with timeout.
    
    Args:
        operation: Async operation to execute
        timeout: Timeout in seconds  
        service_name: Name for logging
    """
    try:
        logger.info(f"Starting {service_name} call with {timeout}s timeout")
        result = await asyncio.wait_for(operation, timeout=timeout)
        logger.info(f"Completed {service_name} call successfully")
        return result
    except asyncio.TimeoutError:
        logger.error(f"{service_name} call timed out after {timeout}s")
        raise HTTPException(
            status_code=503,
            detail=f"{service_name} is temporarily unavailable. Please try again."
        )