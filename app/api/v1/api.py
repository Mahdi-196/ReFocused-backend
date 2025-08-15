from fastapi import APIRouter

from app.api.v1.endpoints import auth, content, goals, users, study, statistics, journal, admin, ai
from app.routers import monitoring, habits, streak, mood, dashboard, calendar, time

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(content.router, prefix="/content", tags=["content"])
api_router.include_router(users.router, prefix="/user", tags=["users"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
# NOTE: legacy routers removed to avoid duplication; ensure equivalent v1 endpoints exist
api_router.include_router(statistics.router, prefix="/statistics", tags=["statistics"])
api_router.include_router(journal.router, prefix="/journal", tags=["journal"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(study.router, prefix="/study/sets", tags=["study"])  # Study sets API
api_router.include_router(habits.router, prefix="/habits", tags=["habits"])
api_router.include_router(streak.router, prefix="/streak", tags=["streak"])
api_router.include_router(mood.router, prefix="/mood", tags=["mood"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(calendar.router, tags=["calendar"])  # Calendar router defines its own prefix
api_router.include_router(time.router, prefix="/time", tags=["time"])

# Export monitoring router for root-level mounting (for /metrics, /health endpoints)
monitoring_router = APIRouter()
monitoring_router.include_router(monitoring.router, tags=["monitoring"])
