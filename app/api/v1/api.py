from fastapi import APIRouter

from app.api.v1.endpoints import auth, content, users, goals
from app.routers import habits, mood, dashboard

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(content.router, prefix="/content", tags=["content"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
api_router.include_router(habits.router, prefix="/habits", tags=["habits"])
api_router.include_router(mood.router, prefix="/mood", tags=["mood"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"]) 