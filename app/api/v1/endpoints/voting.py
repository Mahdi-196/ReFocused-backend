from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx
from typing import Dict

from ....core.auth import get_current_user
from ....db.models import User
from ....services.voting_service import voting_service
from ....schemas.voting import VoteRequest, VoteResponse, VoteStatsResponse, FeatureTallyItem
from ....utils.security import get_client_ip
from ....caching.redis_cache import cache
from ....core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text as sql_text
from ....db.database import get_db


router = APIRouter()


def _seconds_until_midnight_utc() -> int:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((reset - now).total_seconds())

_ip_counts_fallback: dict[str, dict] = {}


@router.post("/vote", response_model=VoteResponse, summary="Cast a feature vote")
async def cast_vote(
    payload: VoteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VoteResponse:
    try:
        # Soft IP+day limit via Redis
        ip_limit = settings.VOTING_IP_DAILY_LIMIT
        ip = get_client_ip(request)
        from datetime import datetime, timezone
        date_key = datetime.now(timezone.utc).date().isoformat()
        ip_key = f"voting:ip:{ip}:{date_key}"
        ttl_hint = _seconds_until_midnight_utc()
        ip_count = await cache.increment(ip_key, 1, ttl_hint) if cache.enabled else 1
        ttl_seconds = await cache.get_ttl(ip_key) if cache.enabled else ttl_hint
        ttl_seconds = ttl_seconds if ttl_seconds is not None else ttl_hint
        if ip_count > ip_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many voting requests today",
                headers={"Retry-After": str(ttl_seconds)},
            )

        # Enforce one vote per account (Redis fast-path + Postgres authoritative)
        # 1) Redis fast-path
        voted_key = f"voted:user:{current_user.id}"
        if cache.enabled and await cache.exists(voted_key):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have already voted")

        # 2) Postgres authoritative check
        exists_sql = sql_text("SELECT 1 FROM user_feature_votes WHERE user_id = :uid LIMIT 1")
        res = await db.execute(exists_sql, {"uid": current_user.id})
        row = res.first()
        if row is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have already voted")

        # Determine voteId: prefer predefined slug; otherwise use trimmed custom
        if payload.feature:
            vote_id = payload.feature
        else:
            vote_id = payload.custom.strip()  # validated length <= 600

        result = await voting_service.cast_vote(vote_id=vote_id)

        # Record the vote (idempotent constraint on user_id handled in migration)
        insert_sql = sql_text("INSERT INTO user_feature_votes (user_id, vote_id) VALUES (:uid, :vid) ON CONFLICT (user_id) DO NOTHING")
        await db.execute(insert_sql, {"uid": current_user.id, "vid": vote_id})
        await db.commit()

        # Mark in Redis (long TTL for practical permanence)
        if cache.enabled:
            await cache.set(voted_key, 1, ttl=315360000)  # ~10 years
        return VoteResponse(
            status=str(result.get("status", "ok")),
            message=result.get("message"),
            vote_id=str(result.get("vote_id")) if result.get("vote_id") is not None else None,
        )
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else status.HTTP_502_BAD_GATEWAY
        resp_text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=resp_text)
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


@router.get("/me", summary="Check if current user has voted")
async def has_voted(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        # Fast-path via Redis flag
        voted_key = f"voted:user:{current_user.id}"
        if cache.enabled and await cache.exists(voted_key):
            return {"voted": True}

        # Authoritative DB check
        exists_sql = sql_text("SELECT vote_id FROM user_feature_votes WHERE user_id = :uid LIMIT 1")
        res = await db.execute(exists_sql, {"uid": current_user.id})
        row = res.first()
        if row is not None:
            # row[0] is vote_id
            return {"voted": True, "vote_id": str(row[0]) if row[0] is not None else None}
        return {"voted": False}
    except Exception:
        # On any storage error, default to not voted rather than breaking UI
        return {"voted": False}

