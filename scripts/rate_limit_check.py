"""
Simple script to verify 429 behavior when RATE_LIMIT_ENABLED=true.

Usage:
  APP_ENV=production RATE_LIMIT_ENABLED=true python scripts/rate_limit_check.py --url http://localhost:8000/api/v1/auth/login --requests 200 --concurrency 20
"""

import argparse
import asyncio
import os
from typing import List
import httpx


async def worker(client: httpx.AsyncClient, url: str, results: List[int], requests: int):
    for _ in range(requests):
        try:
            resp = await client.get(url)
            results.append(resp.status_code)
        except Exception:
            results.append(0)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    # Ensure production/rate limit enabled for server side
    os.environ.setdefault("APP_ENV", "production")
    os.environ.setdefault("RATE_LIMIT_ENABLED", "true")

    results: List[int] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        tasks = [
            asyncio.create_task(worker(client, args.url, results, args.requests // args.concurrency))
            for _ in range(args.concurrency)
        ]
        await asyncio.gather(*tasks)

    total = len(results)
    ok = sum(1 for s in results if 200 <= s < 300)
    ratelimited = sum(1 for s in results if s == 429)
    errors = sum(1 for s in results if s == 0 or s >= 500)
    print({
        "total": total,
        "ok": ok,
        "ratelimited": ratelimited,
        "errors": errors,
    })


if __name__ == "__main__":
    asyncio.run(main())


