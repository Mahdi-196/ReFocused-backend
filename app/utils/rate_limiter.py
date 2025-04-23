from fastapi import HTTPException, Request
from functools import wraps
import time
from collections import defaultdict
from app.core.security_config import security_config

# Simple in-memory store for rate limiting
# In production, use Redis or similar
rate_limit_store = defaultdict(list)

def rate_limit():
    """Rate limiting decorator."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not security_config.RATE_LIMIT_ENABLED:
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
                if current_time - req_time < security_config.RATE_LIMIT_PERIOD_SECONDS
            ]
            
            # Check rate limit
            if len(rate_limit_store[client_ip]) >= security_config.RATE_LIMIT_MAX_REQUESTS:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later."
                )
            
            # Add current request
            rate_limit_store[client_ip].append(current_time)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator 