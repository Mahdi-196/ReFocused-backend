from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx
from typing import Dict

from ....core.auth import get_current_user
from ....db.models import User
from ....services.voting_service import voting_service
from ....schemas.voting import VoteRequest, VoteResponse, VoteStatsResponse, FeatureTallyItem


router = APIRouter()


def _client_ip(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

_ip_counts_fallback: dict[str, dict] = {}


@router.post("/vote", response_model=VoteResponse, summary="Cast a feature vote")
async def cast_vote(
    payload: VoteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> VoteResponse:
    try:
        # Simple IP+day rate limit (in-memory only)
        limit = 100
        ip = _client_ip(request)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        reset_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        now_ts = now.timestamp()
        rec = _ip_counts_fallback.get(ip)
        if not rec or now_ts >= rec["reset_at"]:
            rec = {"count": 0, "reset_at": reset_dt.timestamp()}
        rec["count"] += 1
        _ip_counts_fallback[ip] = rec
        count = rec["count"]
        ttl_seconds = max(1, int(rec["reset_at"] - now_ts))

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many voting requests today",
                headers={"Retry-After": str(ttl_seconds)},
            )

        # Determine voteId: prefer predefined slug; otherwise use trimmed custom
        if payload.feature:
            vote_id = payload.feature
        else:
            vote_id = payload.custom.strip()  # validated length <= 600

        result = await voting_service.cast_vote(vote_id=vote_id)
        return VoteResponse(
            status=str(result.get("status", "ok")),
            message=result.get("message"),
            vote_id=str(result.get("vote_id")) if result.get("vote_id") is not None else None,
        )
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else status.HTTP_502_BAD_GATEWAY
        text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Voting upstream error: {e}")


@router.get("/stats", response_model=VoteStatsResponse, summary="Get voting statistics")
async def vote_stats(
    current_user: User = Depends(get_current_user),
) -> VoteStatsResponse:
    try:
        data: Dict = await voting_service.stats()
        total = int(data.get("total", 0))
        items_raw = data.get("items", [])
        items = [FeatureTallyItem(key=str(i.get("key")), votes=int(i.get("votes", 0))) for i in items_raw]
        return VoteStatsResponse(total=total, items=items)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Voting upstream error: {e}")


