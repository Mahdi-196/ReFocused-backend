from fastapi import APIRouter, HTTPException, status, Request
import httpx
import logging

from app.api.v1.endpoints import auth, goals, users, study, statistics, journal, admin, ai, voting, feedback
from app.routers import monitoring, habits, streak, mood, dashboard, calendar, time
from pydantic import BaseModel, validator
from app.services.email_service import email_service
from app.caching.redis_cache import cache
from app.core.config import settings
from app.utils.security import get_client_ip

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

api_router.include_router(users.router, prefix="/user", tags=["users"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
# NOTE: legacy routers removed to avoid duplication; ensure equivalent v1 endpoints exist
api_router.include_router(statistics.router, prefix="/statistics", tags=["statistics"])
api_router.include_router(journal.router, prefix="/journal", tags=["journal"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(voting.router, prefix="/voting", tags=["voting"])
api_router.include_router(feedback.router, tags=["feedback"])  # routes define their own prefix
api_router.include_router(study.router, prefix="/study/sets", tags=["study"])  # Study sets API
api_router.include_router(habits.router, prefix="/habits", tags=["habits"])
api_router.include_router(streak.router, prefix="/streak", tags=["streak"])
api_router.include_router(mood.router, prefix="/mood", tags=["mood"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(calendar.router, tags=["calendar"])  # Calendar router defines its own prefix
api_router.include_router(time.router, prefix="/time", tags=["time"])


class EmailRequest(BaseModel):
    email: str

    @validator('email')
    def validate_email(cls, v):
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower().strip()


def _seconds_until_midnight_utc() -> int:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((reset - now).total_seconds())


@api_router.post("/email/refocusedSubscribe", tags=["email"], summary="Subscribe (proxied)")
async def proxy_email_subscribe(payload: EmailRequest, request: Request) -> dict:
    try:
        # Per-IP daily limit
        ip_limit = settings.EMAIL_SUBSCRIPTION_DAILY_LIMIT
        ip = get_client_ip(request)
        from datetime import datetime, timezone
        date_key = datetime.now(timezone.utc).date().isoformat()
        # Unified key so subscribe+unsubscribe share the same daily budget
        ip_key = f"email:actions:ip:{ip}:{date_key}"
        ttl_hint = _seconds_until_midnight_utc()
        ip_count = await cache.increment(ip_key, 1, ttl_hint) if cache.enabled else 1
        ttl_seconds = await cache.get_ttl(ip_key) if cache.enabled else ttl_hint
        ttl_seconds = ttl_seconds if ttl_seconds is not None else ttl_hint
        logging.getLogger(__name__).debug(
            "email_subscribe_rl ip=%s key=%s count=%s limit=%s ttl=%s",
            ip, ip_key, ip_count, ip_limit, ttl_seconds
        )
        if ip_count > ip_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many subscription attempts today",
                headers={"Retry-After": str(ttl_seconds)},
            )

        return await email_service.subscribe(payload.email)
    except HTTPException:
        # Preserve 429 or any explicit errors we raised above
        raise
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 502
        text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=text)
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Email subscribe upstream error")


@api_router.post("/email/unsubscribe", tags=["email"], summary="Unsubscribe (proxied)")
async def proxy_email_unsubscribe(payload: EmailRequest, request: Request) -> dict:
    try:
        # Apply same per-IP daily limit to unsubscribe so total actions <= limit
        ip_limit = settings.EMAIL_SUBSCRIPTION_DAILY_LIMIT
        ip = get_client_ip(request)
        from datetime import datetime, timezone
        date_key = datetime.now(timezone.utc).date().isoformat()
        ip_key = f"email:actions:ip:{ip}:{date_key}"
        ttl_hint = _seconds_until_midnight_utc()
        ip_count = await cache.increment(ip_key, 1, ttl_hint) if cache.enabled else 1
        ttl_q = await cache.get_ttl(ip_key) if cache.enabled else None
        ttl_seconds = ttl_q if ttl_q is not None else ttl_hint
        logging.getLogger(__name__).debug(
            "email_unsubscribe_rl ip=%s key=%s count=%s limit=%s ttl=%s",
            ip, ip_key, ip_count, ip_limit, ttl_seconds
        )
        if ip_count > ip_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many email list actions today",
                headers={"Retry-After": str(ttl_seconds)},
            )
        return await email_service.unsubscribe(payload.email)
    except HTTPException:
        # Preserve explicit 4xx (e.g., 429) from our rate limiter
        raise
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 502
        text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=text)
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Email unsubscribe upstream error")


@api_router.post("/email/status", tags=["email"], summary="Status (proxied)")
async def proxy_email_status(payload: EmailRequest, request: Request) -> dict:
    try:
        return await email_service.status(payload.email)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 502
        text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=text)
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Email status upstream error")

# Export monitoring router for root-level mounting (for /metrics, /health endpoints)
monitoring_router = APIRouter()
monitoring_router.include_router(monitoring.router, tags=["monitoring"])
