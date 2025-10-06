#!/usr/bin/env python3
"""
Clear rate limit keys from Redis cache
"""
import asyncio
import sys
import os

# Add the app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

async def clear_rate_limits():
    """Clear all rate limit keys from Redis"""
    try:
        from app.caching.redis_cache import cache

        print("🔌 Connecting to Redis...")

        if not cache.enabled:
            print("❌ Redis cache is not enabled")
            return

        print("✅ Redis connected")

        # Scan for rate limit keys
        print("🔍 Scanning for rate limit keys...")
        cursor = 0
        keys_deleted = 0

        while True:
            cursor, keys = await cache._redis.scan(cursor, match="rate_limit:*", count=100)

            if keys:
                print(f"🗑️  Found {len(keys)} rate limit keys, deleting...")
                for key in keys:
                    await cache._redis.delete(key)
                    keys_deleted += 1
                    print(f"   Deleted: {key.decode() if isinstance(key, bytes) else key}")

            if cursor == 0:
                break

        print(f"\n✅ Successfully deleted {keys_deleted} rate limit keys")

    except Exception as e:
        print(f"❌ Error clearing rate limits: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧹 Rate Limit Cache Cleaner\n")
    asyncio.run(clear_rate_limits())
