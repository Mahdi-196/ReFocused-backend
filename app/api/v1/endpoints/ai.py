from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer
from typing import Dict, Any
import logging
from datetime import datetime, timedelta, timezone

from ....services.ai_service import ai_service
from ....schemas.ai import (
    QuoteResponse, WordResponse, MindFuelResponse, ChatRequest, ChatResponse,
    ContentPopulationRequest, ContentPopulationResponse, AIErrorResponse,
    WritingPromptsResponse, AiSuggestionsResponse, WeeklyThemeResponse,
    ChatQuotaResponse,
)
from ....core.auth import get_current_user
from ....db.models import User
from ....caching.redis_cache import cache
from ....core.config import settings
from ....utils.security import get_client_ip

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

# In-memory fallback for per-IP counts when Redis is unavailable (single-process only).
_ip_counts_fallback = {}

def _get_client_ip(request: Request) -> str:
    return get_client_ip(request)

def _seconds_until_midnight_utc() -> int:
    """Seconds remaining until next UTC midnight."""
    now = datetime.now(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((reset - now).total_seconds())

@router.get(
    "/chat/quota",
    response_model=ChatQuotaResponse,
    summary="Get AI chat quotas",
    description="Return remaining and reset seconds for user and IP daily chat quotas"
)
async def get_chat_quota(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> ChatQuotaResponse:
    ip_limit = settings.AI_CHAT_DAILY_LIMIT
    user_limit = settings.AI_CHAT_DAILY_LIMIT
    ip = _get_client_ip(request)
    date_key = datetime.now(timezone.utc).date().isoformat()
    ip_key = f"ai:chat:ip:{ip}:{date_key}"
    user_key = f"ai:chat:user:{current_user.id}:{date_key}"
    ttl_hint = _seconds_until_midnight_utc()

    ip_count = 0
    user_count = 0
    ip_ttl = ttl_hint
    user_ttl = ttl_hint
    if cache.enabled:
        raw_ip = await cache.get(ip_key)
        raw_user = await cache.get(user_key)
        try:
            ip_count = int(raw_ip) if raw_ip is not None else 0
        except Exception:
            ip_count = 0
        try:
            user_count = int(raw_user) if raw_user is not None else 0
        except Exception:
            user_count = 0
        t1 = await cache.get_ttl(ip_key)
        t2 = await cache.get_ttl(user_key)
        ip_ttl = t1 if t1 is not None else ttl_hint
        user_ttl = t2 if t2 is not None else ttl_hint

    return ChatQuotaResponse(
        user_remaining=max(0, user_limit - user_count),
        user_reset_seconds=user_ttl,
        ip_remaining=max(0, ip_limit - ip_count),
        ip_reset_seconds=ip_ttl,
    )

@router.get(
    "/quote-of-day", 
    response_model=QuoteResponse,
    summary="Get Quote of the Day",
    description="Retrieve daily inspirational quote from historical figures with caching"
)
async def get_quote_of_day(
    current_user: User = Depends(get_current_user)
) -> QuoteResponse:
    """Get daily inspirational quote from AWS Lambda with caching"""
    try:
        result = await ai_service.get_quote_of_day()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Quote service temporarily unavailable"
            )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Quote generation failed: {result.get('message', 'Unknown error')}"
            )
        
        return QuoteResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_quote_of_day: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching quote"
        )

@router.get(
    "/word-of-day",
    response_model=WordResponse, 
    summary="Get Word of the Day",
    description="Retrieve daily vocabulary word with anti-repetition logic"
)
async def get_word_of_day(
    current_user: User = Depends(get_current_user)
) -> WordResponse:
    """Get daily vocabulary word from AWS Lambda with anti-repetition"""
    try:
        result = await ai_service.get_word_of_day()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Word service temporarily unavailable"
            )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Word generation failed: {result.get('message', 'Unknown error')}"
            )
        
        return WordResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_word_of_day: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching word"
        )

@router.get(
    "/mind-fuel",
    response_model=MindFuelResponse,
    summary="Get Mind Fuel",
    description="Retrieve comprehensive daily content with 5 sections for productivity and mindfulness"
)
async def get_mind_fuel(
    current_user: User = Depends(get_current_user)
) -> MindFuelResponse:
    """Get daily mind fuel content from AWS Lambda"""
    try:
        result = await ai_service.get_mind_fuel()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mind fuel service temporarily unavailable"
            )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Mind fuel generation failed: {result.get('message', 'Unknown error')}"
            )
        
        return MindFuelResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_mind_fuel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching mind fuel"
        )

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="AI Chat",
    description="Interactive AI chat with rate limiting (50 messages per day per IP)"
)
async def ai_chat(
    chat_request: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> ChatResponse:
    """Send message to AI chat via AWS Lambda with per-IP rate limiting"""
    try:
        # Enforce per-IP and per-user daily quotas
        ip_limit = settings.AI_CHAT_DAILY_LIMIT
        user_limit = settings.AI_CHAT_DAILY_LIMIT
        ip = _get_client_ip(request)
        date_key = datetime.now(timezone.utc).date().isoformat()
        ip_key = f"ai:chat:ip:{ip}:{date_key}"
        user_key = f"ai:chat:user:{current_user.id}:{date_key}"
        ttl_hint = _seconds_until_midnight_utc()

        # Increment IP and user keys (if Redis enabled)
        ip_count = await cache.increment(ip_key, 1, ttl_hint) if cache.enabled else None
        user_count = await cache.increment(user_key, 1, ttl_hint) if cache.enabled else None
        ttl_q_ip = await cache.get_ttl(ip_key) if cache.enabled else None
        ttl_q_user = await cache.get_ttl(user_key) if cache.enabled else None
        ip_ttl = ttl_q_ip if ttl_q_ip is not None else ttl_hint
        user_ttl = ttl_q_user if ttl_q_user is not None else ttl_hint
        ttl_seconds = min(ip_ttl, user_ttl)

        # In fallback mode (no Redis), track only IP as before
        if ip_count is None or user_count is None:
            # Fallback: track in-memory for single-process runs (IP only)
            now_ts = datetime.now(timezone.utc).timestamp()
            rec = _ip_counts_fallback.get(ip)
            if not rec or now_ts >= rec["reset_at"]:
                reset_dt = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                rec = {"count": 0, "reset_at": reset_dt.timestamp()}
            rec["count"] += 1
            _ip_counts_fallback[ip] = rec
            ip_count = rec["count"]
            ip_ttl = max(1, int(rec["reset_at"] - now_ts))
            user_count = 0
            user_ttl = ttl_hint
            ttl_seconds = min(ip_ttl, user_ttl)

        # Enforce both limits
        if ip_count > ip_limit or user_count > user_limit:
            # Block and expose reset for frontend throttling
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily message limit exceeded",
                headers={"Retry-After": str(ttl_seconds)}
            )

        ip_remaining = max(0, ip_limit - ip_count)
        user_remaining = max(0, user_limit - user_count)

        conversation_history = []
        if chat_request.conversation_history:
            conversation_history = [
                {"role": msg.role, "content": msg.content} 
                for msg in chat_request.conversation_history
            ]
        
        result = await ai_service.chat(
            message=chat_request.message,
            user_id=str(current_user.id),
            system_prompt=chat_request.system_prompt,
            conversation_history=conversation_history
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI chat service temporarily unavailable"
            )
        
        if "error" in result:
            if result["error"] == "rate_limit_exceeded":
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Daily message limit exceeded (50 messages per day)"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Chat failed: {result.get('message', 'Unknown error')}"
            )
        
        return ChatResponse(
            response=result["response"],
            messages_remaining=result.get("messages_remaining", 0),
            usage=result.get("usage"),
            ip_remaining=ip_remaining,
            ip_reset_seconds=ip_ttl,
            user_remaining=user_remaining,
            user_reset_seconds=user_ttl,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error in ai_chat: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error during chat: {str(e)}"
        )

@router.post(
    "/populate-data",
    response_model=ContentPopulationResponse,
    summary="Populate Content Data",
    description="Generate bulk content for various content types (journals, goals, etc.)"
)
async def populate_content(
    request: ContentPopulationRequest,
    current_user: User = Depends(get_current_user)
) -> ContentPopulationResponse:
    """Generate bulk content via AWS Lambda"""
    try:
        result = await ai_service.populate_content(
            data_type=request.data_type,
            count=request.count,
            custom_prompt=request.custom_prompt
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Content population service temporarily unavailable"
            )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Content generation failed: {result.get('message', 'Unknown error')}"
            )
        
        return ContentPopulationResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in populate_content: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during content population"
        )

@router.get(
    "/test-auth",
    summary="Test Authentication", 
    description="Test if authentication is working (no external API calls)"
)
async def test_auth(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Test authentication without making external API calls"""
    return {
        "status": "authenticated",
        "user_id": current_user.id,
        "user_email": getattr(current_user, 'email', 'N/A'),
        "message": "Authentication is working properly!"
    }

@router.post(
    "/generate-daily-content",
    summary="Manual Daily Content Generation",
    description="Manually trigger daily content generation (for testing purposes)"
)
async def generate_daily_content(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Manually trigger daily content generation"""
    try:
        from ....core.scheduler import content_scheduler
        
        logger.info(f"Manual daily content generation triggered by user {current_user.id}")
        results = await content_scheduler.trigger_manual_daily_generation()
        
        return {
            "status": "completed",
            "message": "Daily content generation completed",
            "results": results,
            "triggered_by": current_user.id
        }
        
    except Exception as e:
        logger.error(f"Manual content generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate daily content: {str(e)}"
        )

@router.post(
    "/generate-weekly-content",
    summary="Manual Weekly Content Generation",
    description="Manually trigger weekly content generation (for testing purposes)"
)
async def generate_weekly_content(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Manually trigger weekly content generation"""
    try:
        from ....core.scheduler import content_scheduler
        
        logger.info(f"Manual weekly content generation triggered by user {current_user.id}")
        results = await content_scheduler.trigger_manual_weekly_generation()
        
        return {
            "status": "completed",
            "message": "Weekly content generation completed",
            "results": results,
            "triggered_by": current_user.id
        }
        
    except Exception as e:
        logger.error(f"Manual weekly content generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate weekly content: {str(e)}"
        )

@router.get(
    "/scheduler-status",
    summary="Scheduler Status",
    description="Get status of the content scheduler (daily and weekly)"
)
async def get_scheduler_status(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get status of the content scheduler"""
    try:
        from ....core.scheduler import content_scheduler
        
        next_runs = content_scheduler.get_next_run_times()
        
        return {
            "status": "running" if content_scheduler.is_running else "stopped",
            "scheduler_active": content_scheduler.is_running,
            "daily": {
                "next_run": next_runs.get('daily').isoformat() if next_runs and next_runs.get('daily') else None,
                "timezone": str(next_runs.get('daily').tzinfo) if next_runs and next_runs.get('daily') else None
            },
            "weekly": {
                "next_run": next_runs.get('weekly').isoformat() if next_runs and next_runs.get('weekly') else None,
                "timezone": str(next_runs.get('weekly').tzinfo) if next_runs and next_runs.get('weekly') else None
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scheduler status: {str(e)}"
        )

@router.post(
    "/writing-prompts",
    response_model=WritingPromptsResponse,
    summary="Get Weekly Writing Prompts",
    description="Retrieve 5 weekly writing prompts for journal reflection with 7-day caching"
)
async def get_writing_prompts(
    current_user: User = Depends(get_current_user)
) -> WritingPromptsResponse:
    """Get weekly writing prompts from AWS Lambda with caching"""
    try:
        result = await ai_service.get_writing_prompts()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Writing prompts service temporarily unavailable"
            )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Writing prompts generation failed: {result.get('message', 'Unknown error')}"
            )
        
        return WritingPromptsResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_writing_prompts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching writing prompts"
        )

@router.post(
    "/ai-suggestions",
    response_model=AiSuggestionsResponse,
    summary="Get Weekly AI Suggestions",
    description="Retrieve 4 weekly AI assistance prompts with 7-day caching"
)
async def get_ai_suggestions(
    current_user: User = Depends(get_current_user)
) -> AiSuggestionsResponse:
    """Get weekly AI suggestions from AWS Lambda with caching"""
    try:
        result = await ai_service.get_ai_suggestions()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI suggestions service temporarily unavailable"
            )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI suggestions generation failed: {result.get('message', 'Unknown error')}"
            )
        
        return AiSuggestionsResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_ai_suggestions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching AI suggestions"
        )

@router.post(
    "/weekly-theme",
    response_model=WeeklyThemeResponse,
    summary="Get Weekly Theme",
    description="Retrieve the weekly theme for journal reflection with 7-day caching"
)
async def get_weekly_theme(
    current_user: User = Depends(get_current_user)
) -> WeeklyThemeResponse:
    """Get weekly theme from AWS Lambda with caching"""
    try:
        result = await ai_service.get_weekly_theme()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Weekly theme service temporarily unavailable"
            )
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Weekly theme generation failed: {result.get('message', 'Unknown error')}"
            )
        
        return WeeklyThemeResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_weekly_theme: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching weekly theme"
        )

@router.get(
    "/weekly-theme",
    response_model=WeeklyThemeResponse,
    summary="Get Weekly Theme (GET)",
    description="Retrieve the weekly theme (GET alias for compatibility)"
)
async def get_weekly_theme_get(
    current_user: User = Depends(get_current_user)
) -> WeeklyThemeResponse:
    return await get_weekly_theme(current_user)

@router.get(
    "/health",
    summary="Health Check",
    description="Check if AI API Gateway is accessible"
)
async def ai_health_check() -> Dict[str, Any]:
    """Check health of AI API Gateway endpoints"""
    try:
        quote_result = await ai_service.get_quote_of_day()
        
        return {
            "status": "healthy" if quote_result else "degraded",
            "api_gateway": settings.AI_API_BASE_URL,
            "endpoints": {
                "quote_of_day": "accessible" if quote_result else "error",
                "word_of_day": "available",
                "mind_fuel": "available", 
                "chat": "available",
                "populate_data": "available",
                "writing_prompts": "available",
                "ai_suggestions": "available",
                "weekly_theme": "available"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "api_gateway": settings.AI_API_BASE_URL
        }