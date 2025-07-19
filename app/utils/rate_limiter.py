from fastapi import HTTPException, Request
from functools import wraps
import time
from collections import defaultdict
from app.core.config import settings

# Simple in-memory store for rate limiting
# In production, use Redis or similar
rate_limit_store = defaultdict(list)

class RateLimiter:
    """Rate limiter class for API endpoints."""
    
    def __init__(self):
        self.store = defaultdict(list)
    
    async def check_rate_limit(
        self, 
        key: str, 
        max_requests: int, 
        window_seconds: int
    ) -> None:
        """Check if request exceeds rate limit."""
        current_time = time.time()
        
        # Clean old requests
        self.store[key] = [
            req_time for req_time in self.store[key]
            if current_time - req_time < window_seconds
        ]
        
        # Check rate limit
        if len(self.store[key]) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds} seconds."
            )
        
        # Add current request
        self.store[key].append(current_time)

def rate_limit():
    """Rate limiting decorator."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not settings.RATE_LIMIT_ENABLED:
                return await func(*args, **kwargs)
            
            # Get request object
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for arg in kwargs.values():
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if not request:
                return await func(*args, **kwargs)
            
            # Get client IP
            client_ip = request.client.host
            
            # Clean old requests
            current_time = time.time()
            rate_limit_store[client_ip] = [
                req_time for req_time in rate_limit_store[client_ip]
                if current_time - req_time < settings.RATE_LIMIT_PERIOD_SECONDS
            ]
            
            # Check rate limit
            if len(rate_limit_store[client_ip]) >= settings.RATE_LIMIT_MAX_REQUESTS:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later."
                )
            
            # Add current request
            rate_limit_store[client_ip].append(current_time)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator 