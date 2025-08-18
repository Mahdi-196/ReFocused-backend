from fastapi import APIRouter, HTTPException, Request, status, Depends
import httpx
from typing import Dict

from ....core.auth import get_current_user
from ....db.models import User
from ....services.feedback_service import feedback_service
from ....schemas.feedback import FeedbackRequest, FeedbackResponse


router = APIRouter()


def _client_ip(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/feedback", response_model=FeedbackResponse, summary="Submit feedback")
async def submit_feedback(
    payload: FeedbackRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    try:
        # Rate limit: 50 submissions/day per IP (in-memory only)
        limit = 50
        ip = _client_ip(request)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        reset_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        now_ts = now.timestamp()
        # simple module-level counter map
        global _feedback_ip_counts
        try:
            _feedback_ip_counts  # type: ignore[name-defined]
        except NameError:
            _feedback_ip_counts = {}
        rec = _feedback_ip_counts.get(ip)
        if not rec or now_ts >= rec["reset_at"]:
            rec = {"count": 0, "reset_at": reset_dt.timestamp()}
        rec["count"] += 1
        _feedback_ip_counts[ip] = rec
        count = rec["count"]
        ttl_seconds = max(1, int(rec["reset_at"] - now_ts))
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many feedback submissions today",
                headers={"Retry-After": str(ttl_seconds)},
            )

        # Forward to AWS
        result: Dict = await feedback_service.submit(payload.model_dump())
        status_text = str(result.get("status", "ok"))
        return FeedbackResponse(status=status_text, feedbackId=result.get("feedbackId"), message=result.get("message"))
    except httpx.HTTPStatusError as e:
        # Preserve upstream status and body for transparency
        code = e.response.status_code if e.response is not None else status.HTTP_502_BAD_GATEWAY
        text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Feedback upstream error: {e}")


