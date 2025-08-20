from fastapi import APIRouter, HTTPException, Request, status
import httpx
from typing import Dict
import logging

from ....services.feedback_service import feedback_service
from ....schemas.feedback import FeedbackRequest, FeedbackResponse
from ....caching.redis_cache import cache
from ....core.config import settings
from ....utils.security import get_client_ip


router = APIRouter()


def _seconds_until_midnight_utc() -> int:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((reset - now).total_seconds())


@router.post("/feedback", response_model=FeedbackResponse, summary="Submit feedback")
async def submit_feedback(
    payload: FeedbackRequest,
    request: Request,
) -> FeedbackResponse:
    try:
        # Daily IP limit (count only successful submissions)
        ip_limit = settings.FEEDBACK_DAILY_LIMIT
        ip = get_client_ip(request)
        from datetime import datetime, timezone
        date_key = datetime.now(timezone.utc).date().isoformat()
        ip_key = f"feedback:ip:{ip}:{date_key}"
        ttl_hint = _seconds_until_midnight_utc()

        # Read current count without incrementing
        ip_count_current = 0
        if cache.enabled:
            raw = await cache.get(ip_key)
            try:
                ip_count_current = int(raw) if raw is not None else 0
            except Exception:
                ip_count_current = 0
            ttl_q = await cache.get_ttl(ip_key)
            ttl_seconds = ttl_q if ttl_q is not None else ttl_hint
        else:
            ttl_seconds = ttl_hint

        if ip_count_current >= ip_limit:
            # Already reached the daily successful-submission limit
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many feedback submissions today",
                headers={"Retry-After": str(ttl_seconds)},
            )

        # Forward to AWS
        result: Dict = await feedback_service.submit(payload.model_dump())
        status_text = str(result.get("status", "ok"))

        # Increment only after successful upstream submission
        if cache.enabled:
            try:
                await cache.increment(ip_key, 1, ttl_hint)
            except Exception:
                # Non-fatal: don't block response if cache increment fails
                logging.getLogger(__name__).warning("Feedback RL increment failed for %s", ip_key)

        return FeedbackResponse(status=status_text, feedbackId=result.get("feedbackId"), message=result.get("message"))
    except HTTPException:
        # Preserve explicit 4xx
        raise
    except httpx.HTTPStatusError as e:
        # Preserve upstream status and body for transparency
        code = e.response.status_code if e.response is not None else status.HTTP_502_BAD_GATEWAY
        text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Feedback upstream error: {e}")


