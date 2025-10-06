import time
import logging
from typing import Dict, Optional, Tuple
from fastapi import Request, HTTPException, status
from functools import wraps
from collections import defaultdict
from app.caching.redis_cache import cache
from app.utils.security import get_client_ip
from app.core.config import settings

logger = logging.getLogger("rate_limiter")

# Fallback in-memory store
rate_limit_store = defaultdict(list)

class AdvancedRateLimiter:
    """Advanced rate limiter with sliding window and Redis backend."""
    
    def __init__(self):
        self.redis = cache if cache.enabled else None
        
    def get_rate_limit_key(self, request: Request, endpoint: str) -> str:
        """Generate rate limiting key considering user ID when available."""
        # Try to get user ID from request state
        if hasattr(request.state, 'user_id') and request.state.user_id:
            return f"rate_limit:{endpoint}:user:{request.state.user_id}"
        
        # Fallback to IP address
        client_ip = get_client_ip(request)
        return f"rate_limit:{endpoint}:ip:{client_ip}"
    
    async def check_rate_limit(
        self, 
        key: str, 
        limit: int, 
        window: int
    ) -> Dict[str, any]:
        """
        Sliding window rate limiting.
        
        Args:
            key: Rate limiting key
            limit: Maximum requests allowed
            window: Time window in seconds
            
        Returns:
            Dict with rate limit status
        """
        now = time.time()
        
        if not self.redis:
            # Use in-memory store as fallback
            return await self._check_in_memory(key, limit, window, now)
        
        try:
            # Use Redis for distributed rate limiting
            return await self._check_redis(key, limit, window, now)
            
        except Exception as e:
            logger.error(f"Redis rate limiting error: {str(e)}, falling back to memory")
            return await self._check_in_memory(key, limit, window, now)
    
    async def _check_redis(self, key: str, limit: int, window: int, now: float) -> Dict[str, any]:
        """Redis-based rate limiting."""
        # Remove expired entries (older than window)
        await self.redis.delete_expired(key, now - window)
        
        # Count current requests
        current_count = await self.redis.count_keys(f"{key}:*")
        
        if current_count >= limit:
            return {
                "allowed": False,
                "current": current_count,
                "limit": limit,
                "reset_time": now + window,
                "retry_after": window
            }
        
        # Add current request with timestamp
        timestamp_key = f"{key}:{now}"
        await self.redis.set(timestamp_key, "1", ttl=window + 60)  # Extra TTL for cleanup
        
        return {
            "allowed": True,
            "current": current_count + 1,
            "limit": limit,
            "reset_time": now + window,
            "retry_after": 0
        }
    
    async def _check_in_memory(self, key: str, limit: int, window: int, now: float) -> Dict[str, any]:
        """In-memory fallback rate limiting."""
        # Clean old requests
        rate_limit_store[key] = [
            req_time for req_time in rate_limit_store[key]
            if now - req_time < window
        ]
        
        current_count = len(rate_limit_store[key])
        
        if current_count >= limit:
            return {
                "allowed": False,
                "current": current_count,
                "limit": limit,
                "reset_time": now + window,
                "retry_after": window
            }
        
        # Add current request
        rate_limit_store[key].append(now)
        
        return {
            "allowed": True,
            "current": current_count + 1,
            "limit": limit,
            "reset_time": now + window,
            "retry_after": 0
        }
    
    async def apply_rate_limit(
        self,
        request: Request,
        endpoint: str,
        limit: int,
        window: int
    ) -> None:
        """Apply rate limiting and raise HTTPException if exceeded."""
        if not settings.RATE_LIMIT_ENABLED:
            return
            
        key = self.get_rate_limit_key(request, endpoint)
        result = await self.check_rate_limit(key, limit, window)
        
        if not result["allowed"]:
            # Log rate limit violation
            client_ip = get_client_ip(request)
            logger.warning(f"Rate limit exceeded for {client_ip} on {endpoint}: {result['current']}/{result['limit']}")
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": result["limit"],
                    "window": window,
                    "current": result["current"],
                    "retry_after": result["retry_after"]
                },
                headers={
                    "Retry-After": str(result["retry_after"]),
                    "X-RateLimit-Limit": str(result["limit"]),
                    "X-RateLimit-Remaining": str(max(0, result["limit"] - result["current"])),
                    "X-RateLimit-Reset": str(int(result["reset_time"]))
                }
            )

# Global rate limiter instance
rate_limiter = AdvancedRateLimiter()

# Rate limiting configurations for different endpoint types
class RateLimitConfig:
    """Rate limiting configuration for different endpoint types."""
    
    # Authentication endpoints (stricter limits)
    LOGIN = {"limit": 5, "window": 900}  # 5 attempts per 15 minutes
    REGISTER = {"limit": 3, "window": 3600}  # 3 registrations per hour
    PASSWORD_RESET = {"limit": 3, "window": 3600}  # 3 reset attempts per hour
    
    # API endpoints (moderate limits)
    FEEDBACK = {"limit": 3, "window": 300}  # 3 feedback submissions per 5 minutes
    JOURNAL_WRITE = {"limit": 100, "window": 3600}  # 100 entries per hour
    
    # General API (generous limits)
    GENERAL_READ = {"limit": 1000, "window": 3600}  # 1000 reads per hour
    GENERAL_WRITE = {"limit": 200, "window": 3600}  # 200 writes per hour

async def apply_auth_rate_limit(request: Request, endpoint_type: str = "login"):
    """Apply rate limiting for authentication endpoints."""
    config_map = {
        "login": RateLimitConfig.LOGIN,
        "register": RateLimitConfig.REGISTER,
        "password_reset": RateLimitConfig.PASSWORD_RESET
    }

    config = config_map.get(endpoint_type, RateLimitConfig.LOGIN)
    await rate_limiter.apply_rate_limit(
        request,
        f"auth_{endpoint_type}",
        config["limit"],
        config["window"]
    )

async def apply_api_rate_limit(request: Request, endpoint_type: str = "general_write"):
    """Apply rate limiting for API endpoints."""
    config_map = {
        "feedback": RateLimitConfig.FEEDBACK,
        "journal_write": RateLimitConfig.JOURNAL_WRITE,
        "general_read": RateLimitConfig.GENERAL_READ,
        "general_write": RateLimitConfig.GENERAL_WRITE
    }
    
    config = config_map.get(endpoint_type, RateLimitConfig.GENERAL_WRITE)
    await rate_limiter.apply_rate_limit(
        request,
        f"api_{endpoint_type}",
        config["limit"],
        config["window"]
    )

# Legacy decorator for backward compatibility
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
            
            if request:
                await apply_api_rate_limit(request, "general_write")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator 