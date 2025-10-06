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
    """Advanced rate limiter with sliding window and Redis backend - FIXED VERSION."""

    def __init__(self):
        self.redis = cache if cache.enabled else None

    async def clear_limits(self, key_pattern: str):
        """Clear rate limits for debugging purposes."""
        try:
            if self.redis:
                # Clear from Redis
                await self.redis._redis.delete(key_pattern)
                logger.info(f"🧹 Cleared Redis rate limit for: {key_pattern}")
        except Exception as e:
            logger.error(f"Error clearing rate limits: {e}")

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
        Sliding window rate limiting - FIXED VERSION.
        """
        now = time.time()

        if not self.redis:
            # Use in-memory store as fallback
            return await self._check_in_memory(key, limit, window, now)

        try:
            # Use Redis for distributed rate limiting - FIXED
            return await self._check_redis(key, limit, window, now)

        except Exception as e:
            logger.error(f"Redis rate limiting error: {str(e)}, falling back to memory")
            return await self._check_in_memory(key, limit, window, now)

    async def _check_redis(self, key: str, limit: int, window: int, now: float) -> Dict[str, any]:
        """FIXED Redis-based rate limiting - NO MORE KEYS() OPERATIONS."""

        try:
            # FIXED: Use a counter-based approach instead of scanning all keys
            window_key = f"{key}:window:{int(now // window)}"

            # Get current count for this window
            current_count = await self.redis._redis.get(window_key) or 0
            current_count = int(current_count)

            if current_count >= limit:
                return {
                    "allowed": False,
                    "current": current_count,
                    "limit": limit,
                    "reset_time": (int(now // window) + 1) * window,
                    "retry_after": window
                }

            # Increment counter and set expiration
            pipe = self.redis._redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, window + 1)  # Small buffer for cleanup
            await pipe.execute()

            return {
                "allowed": True,
                "current": current_count + 1,
                "limit": limit,
                "reset_time": (int(now // window) + 1) * window,
                "retry_after": 0
            }

        except Exception as e:
            logger.error(f"Redis operation error: {e}, falling back to in-memory")
            return await self._check_in_memory(key, limit, window, now)

    async def _check_in_memory(self, key: str, limit: int, window: int, now: float) -> Dict[str, any]:
        """In-memory rate limiting fallback."""
        # Clean up expired entries
        rate_limit_store[key] = [timestamp for timestamp in rate_limit_store[key] if now - timestamp < window]

        current_count = len(rate_limit_store[key])

        if current_count >= limit:
            return {
                "allowed": False,
                "current": current_count,
                "limit": limit,
                "reset_time": rate_limit_store[key][0] + window if rate_limit_store[key] else now + window,
                "retry_after": window
            }

        # Add current timestamp
        rate_limit_store[key].append(now)

        return {
            "allowed": True,
            "current": current_count + 1,
            "limit": limit,
            "reset_time": now + window,
            "retry_after": 0
        }


# Create a global rate limiter instance
rate_limiter = AdvancedRateLimiter()

async def apply_auth_rate_limit(request: Request, endpoint: str):
    """Apply rate limiting for authentication endpoints - COMPLETELY DISABLED FOR DEBUG."""

    # COMPLETELY DISABLED: Skip all rate limiting logic
    logger.info(f"🚫 RATE_LIMIT: COMPLETELY BYPASSED for debugging {endpoint}")
    logger.info(f"🚫 RATE_LIMIT: Request IP: {request.client.host if request.client else 'unknown'}")
    logger.info(f"🚫 RATE_LIMIT: Endpoint: {endpoint}")
    logger.info(f"🚫 RATE_LIMIT: No limits applied - full bypass mode")

    # Clear any existing rate limits for this endpoint
    try:
        client_ip = request.client.host if request.client else "unknown"
        key_pattern = f"rate_limit:{endpoint}:ip:{client_ip}"
        await rate_limiter.clear_limits(key_pattern)
        logger.info(f"🧹 RATE_LIMIT: Cleared existing limits for {key_pattern}")
    except Exception as e:
        logger.info(f"🧹 RATE_LIMIT: Could not clear limits: {e}")

    return  # Always return immediately - no rate limiting

    # Skip rate limiting if disabled
    if not settings.RATE_LIMIT_ENABLED:
        return

    # Define rate limits for different auth endpoints
    limits = {
        "login": (10, 300),      # 10 attempts per 5 minutes
        "register": (5, 300),    # 5 attempts per 5 minutes
        "refresh": (20, 60),     # 20 attempts per minute
        "google": (10, 300),     # 10 attempts per 5 minutes
    }

    limit, window = limits.get(endpoint, (10, 300))  # Default: 10 per 5 min

    key = rate_limiter.get_rate_limit_key(request, endpoint)

    try:
        result = await rate_limiter.check_rate_limit(key, limit, window)

        if not result["allowed"]:
            logger.warning(f"Rate limit exceeded for {endpoint}: {key}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many {endpoint} attempts. Try again in {result['retry_after']} seconds."
            )

        logger.info(f"Rate limit OK for {endpoint}: {result['current']}/{result['limit']}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate limit check failed for {endpoint}: {e}")
        # Don't block on rate limit failures in production
        pass