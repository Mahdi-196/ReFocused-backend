from fastapi import APIRouter, HTTPException, status, Request
import httpx

from app.api.v1.endpoints import auth, goals, users, study, statistics, journal, admin, ai, voting, feedback
from app.routers import monitoring, habits, streak, mood, dashboard, calendar, time
from pydantic import BaseModel, EmailStr
from app.services.email_service import email_service

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
    email: EmailStr


@api_router.post("/email/refocusedSubscribe", tags=["email"], summary="Subscribe (proxied)")
async def proxy_email_subscribe(payload: EmailRequest, request: Request) -> dict:
    try:
        return await email_service.subscribe(payload.email)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else 502
        text = e.response.text if e.response is not None else "Upstream error"
        raise HTTPException(status_code=code, detail=text)
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Email subscribe upstream error")


@api_router.post("/email/unsubscribe", tags=["email"], summary="Unsubscribe (proxied)")
async def proxy_email_unsubscribe(payload: EmailRequest, request: Request) -> dict:
    try:
        return await email_service.unsubscribe(payload.email)
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
