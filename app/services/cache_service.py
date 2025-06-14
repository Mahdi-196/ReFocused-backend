from typing import Dict, Any, Optional, TypeVar, Generic, Callable
import time
import threading
import functools

T = TypeVar('T')

class CacheEntry(Generic[T]):
    """A cache entry with expiration."""
    
    def __init__(self, value: T, ttl: int):
        """
        Initialize a cache entry.
        
        Args:
            value: The value to cache
            ttl: Time to live in seconds
        """
        self.value = value
        self.expiration = time.time() + ttl
    
    def is_expired(self) -> bool:
        """Check if the entry is expired."""
        return time.time() > self.expiration


class CacheService:
    """
    Simple in-memory cache service.
    
    This provides a thread-safe in-memory cache with key expiration.
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialize the cache service.
        
        Args:
            default_ttl: Default time to live in seconds
        """
        self.cache: Dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl
        self.lock = threading.RLock()
        
        # Start periodic cleanup
        self._start_cleanup()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found or expired
        """
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if not entry.is_expired():
                    return entry.value
                
                # Remove expired entry
                del self.cache[key]
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set a value in the cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds, or None to use default
        """
        ttl = ttl if ttl is not None else self.default_ttl
        entry = CacheEntry(value, ttl)
        
        with self.lock:
            self.cache[key] = entry
    
    def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was found, False otherwise
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
        
        return False
    
    def clear(self) -> None:
        """Clear the entire cache."""
        with self.lock:
            self.cache.clear()
    
    def cleanup(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        expired_keys = []
        
        with self.lock:
            # Find expired keys
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            # Delete expired keys
            for key in expired_keys:
                del self.cache[key]
        
        return len(expired_keys)
    
    def _start_cleanup(self) -> None:
        """Start periodic cleanup in a background thread."""
        def cleanup_task():
            while True:
                try:
                    time.sleep(60)  # Run every minute
                    self.cleanup()
                except Exception:
                    # Ensure the thread doesn't die
                    pass
        
        cleanup_thread = threading.Thread(
            target=cleanup_task,
            daemon=True,
            name="cache-cleanup"
        )
        cleanup_thread.start()


# Global cache instance
cache = CacheService()


def cached(ttl: Optional[int] = None):
    """
    Decorator to cache function results.
    
    Args:
        ttl: Time to live in seconds, or None to use default
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key_parts = [func.__name__]
            
            # Add positional args to key
            for arg in args:
                key_parts.append(str(arg))
            
            # Add keyword args to key (sorted for consistency)
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v}")
            
            cache_key = ":".join(key_parts)
            
            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    
    return decorator 