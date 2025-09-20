"""
Production Redis caching for performance optimization.
"""

import json
import pickle
import hashlib
from typing import Any, Optional, Dict, List, Union, Callable
from datetime import timedelta
import asyncio
from functools import wraps

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
import platform
from app.monitoring.logging_config import get_logger
from app.monitoring.metrics import CACHE_HITS, CACHE_MISSES

logger = get_logger("cache")

class RedisCache:
    """Production Redis cache with connection pooling and error handling."""
    
    def __init__(self):
        self._redis: Optional[Redis] = None
        self._connection_pool = None
        self.enabled = hasattr(settings, 'REDIS_URL') and settings.REDIS_URL
        
        if self.enabled:
            self._setup_connection()
    
    def _setup_connection(self):
        """Setup Redis connection with proper configuration."""
        try:
            pool_kwargs = dict(
                encoding="utf-8",
                decode_responses=False,  # We handle serialization manually
                retry_on_timeout=True,
                socket_keepalive=True,
                max_connections=20,
            )
            # Avoid invalid keepalive options on non-Linux platforms
            if platform.system() == "Linux":
                pool_kwargs["socket_keepalive_options"] = {
                    1: 1,  # TCP_KEEPIDLE
                    2: 3,  # TCP_KEEPINTVL
                    3: 5,  # TCP_KEEPCNT
                }

            self._connection_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                **pool_kwargs,
            )
            self._redis = redis.Redis(connection_pool=self._connection_pool)
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache: {e}")
            self.enabled = False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with automatic deserialization."""
        if not self.enabled:
            return None
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            cached_data = await self._redis.get(key)
            if cached_data is None:
                CACHE_MISSES.labels(cache_type="redis").inc()
                return None
            
            # Deserialize based on data type marker
            if cached_data.startswith(b'json:'):
                result = json.loads(cached_data[5:].decode('utf-8'))
            elif cached_data.startswith(b'pickle:'):
                result = pickle.loads(cached_data[7:])
            else:
                # Fallback to string
                result = cached_data.decode('utf-8')
            
            duration = asyncio.get_event_loop().time() - start_time
            CACHE_HITS.labels(cache_type="redis").inc()
            if settings.REDIS_CACHE_DEBUG:
                logger.debug(f"Cache hit for key: {key[:50]}... (duration: {duration:.3f}s)")
            return result
            
        except (RedisError, json.JSONDecodeError, pickle.PickleError) as e:
            logger.warning(f"Cache get error for key {key}: {e}")
            CACHE_MISSES.labels(cache_type="redis").inc()
            return None
        except Exception as e:
            logger.error(f"Unexpected cache error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300, serialize_method: str = "auto") -> bool:
        """Set value in cache with TTL and serialization."""
        if not self.enabled:
            return False
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Determine serialization method
            if serialize_method == "auto":
                if isinstance(value, (dict, list)):
                    serialize_method = "json"
                elif isinstance(value, (str, int, float, bool)):
                    serialize_method = "json"
                else:
                    serialize_method = "pickle"
            
            # Serialize data with type marker
            if serialize_method == "json":
                serialized = b'json:' + json.dumps(value, default=str).encode('utf-8')
            elif serialize_method == "pickle":
                serialized = b'pickle:' + pickle.dumps(value)
            else:
                serialized = str(value).encode('utf-8')
            
            await self._redis.setex(key, ttl, serialized)
            
            duration = asyncio.get_event_loop().time() - start_time
            if settings.REDIS_CACHE_DEBUG:
                logger.debug(f"Cache set for key: {key[:50]}... (duration: {duration:.3f}s, ttl: {ttl}s)")
            
            return True
            
        except (RedisError, TypeError, pickle.PickleError) as e:
            logger.warning(f"Cache set error for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self.enabled:
            return False
        
        try:
            result = await self._redis.delete(key)
            if settings.REDIS_CACHE_DEBUG:
                logger.debug(f"Cache delete for key: {key[:50]}...")
            return result > 0
        except RedisError as e:
            logger.warning(f"Cache delete error for key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        if not self.enabled:
            return 0
        
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                result = await self._redis.delete(*keys)
                if settings.REDIS_CACHE_DEBUG:
                    logger.debug(f"Cache delete pattern {pattern}: {result} keys deleted")
                return result
            return 0
        except RedisError as e:
            logger.warning(f"Cache delete pattern error for {pattern}: {e}")
            return 0
    
    async def increment(self, key: str, amount: int = 1, ttl: Optional[int] = None) -> Optional[int]:
        """Increment counter in cache."""
        if not self.enabled:
            return None
        
        try:
            result = await self._redis.incrby(key, amount)
            if ttl and result == amount:  # First time setting the key
                await self._redis.expire(key, ttl)
            return result
        except RedisError as e:
            logger.warning(f"Cache increment error for key {key}: {e}")
            return None
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self.enabled:
            return False
        
        try:
            return await self._redis.exists(key) > 0
        except RedisError as e:
            logger.warning(f"Cache exists error for key {key}: {e}")
            return False
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL for key."""
        if not self.enabled:
            return None
        
        try:
            ttl = await self._redis.ttl(key)
            return ttl if ttl > 0 else None
        except RedisError as e:
            logger.warning(f"Cache TTL error for key {key}: {e}")
            return None
    
    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()


# Global cache instance
cache = RedisCache()


def cache_key(prefix: str, *args, user_id: Optional[int] = None, **kwargs) -> str:
    """Generate consistent cache key."""
    key_parts = [prefix]
    
    if user_id:
        key_parts.append(f"user:{user_id}")
    
    # Add positional arguments
    for arg in args:
        key_parts.append(str(arg))
    
    # Add keyword arguments (sorted for consistency)
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}:{v}")
    
    key = ":".join(key_parts)
    
    # Limit key length and use hash for very long keys
    if len(key) > 200:
        key_hash = hashlib.md5(key.encode()).hexdigest()
        key = f"{prefix}:hash:{key_hash}"
    
    return key


def cached(ttl: int = 300, key_prefix: str = "cache", include_user_id: bool = True):
    """Decorator for caching function results."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract user_id if needed
            user_id = None
            if include_user_id:
                # Try to find user_id in kwargs or args
                user_id = kwargs.get('user_id')
                if not user_id and args:
                    # Check if first arg has user_id attribute (like User object)
                    first_arg = args[0]
                    if hasattr(first_arg, 'id'):
                        user_id = first_arg.id
            
            # Generate cache key
            cache_key_str = cache_key(
                f"{key_prefix}:{func.__name__}",
                *args[1:] if include_user_id and args else args,  # Skip first arg if it's user
                user_id=user_id,
                **{k: v for k, v in kwargs.items() if k != 'user_id'}
            )
            
            # Try to get from cache
            cached_result = await cache.get(cache_key_str)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                await cache.set(cache_key_str, result, ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we can't easily use async cache
            # Just execute the function
            return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


def invalidate_user_cache(user_id: int, patterns: List[str]):
    """Invalidate cache patterns for a specific user."""
    async def _invalidate():
        for pattern in patterns:
            pattern_with_user = pattern.replace("{user_id}", str(user_id))
            await cache.delete_pattern(pattern_with_user)
    
    # Schedule for background execution
    asyncio.create_task(_invalidate())


# Common cache patterns
class CachePatterns:
    """Common cache key patterns for different data types."""
    
    USER_PROFILE = "user:profile:{user_id}"
    USER_HABITS = "user:habits:{user_id}"
    USER_GOALS = "user:goals:{user_id}:*"
    USER_STATISTICS = "user:stats:{user_id}:*"
    HABIT_COMPLETIONS = "habit:completions:{user_id}:*"
    CALENDAR_DATA = "calendar:{user_id}:*"
    
    @classmethod
    def get_user_patterns(cls, user_id: int) -> List[str]:
        """Get all cache patterns for a user."""
        return [
            pattern.format(user_id=user_id) 
            for pattern in [
                cls.USER_PROFILE,
                cls.USER_HABITS,
                cls.USER_GOALS,
                cls.USER_STATISTICS,
                cls.HABIT_COMPLETIONS,
                cls.CALENDAR_DATA
            ]
        ] 