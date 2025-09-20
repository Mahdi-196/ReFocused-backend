"""
Daily Streak Tracking Middleware

Automatically tracks meaningful user interactions across all endpoints
for daily streak calculation without requiring changes to individual endpoints.
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import time
import asyncio
from typing import Dict, Any, Optional

from app.db.database import async_session
from app.services.daily_streak_service import daily_streak_service, InteractionType
from app.core.auth import get_current_user_from_token

logger = logging.getLogger(__name__)

class StreakTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware that automatically tracks meaningful user interactions for daily streaks"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Map endpoint patterns to interaction types
        self.interaction_mapping = {
            # Habits
            ("POST", "/api/v1/habits"): InteractionType.HABIT_CREATION,
            ("POST", "/api/v1/habits/{habit_id}/complete"): InteractionType.HABIT_COMPLETION,
            ("PUT", "/api/v1/habits/{habit_id}/complete/{date}"): InteractionType.HABIT_COMPLETION,
            
            # Goals
            ("POST", "/api/v1/goals"): InteractionType.GOAL_CREATION,
            ("PUT", "/api/v1/goals/{goal_id}/increment"): InteractionType.GOAL_PROGRESS,
            ("PUT", "/api/v1/goals/{goal_id}/complete"): InteractionType.GOAL_PROGRESS,
            
            # Mood tracking
            ("POST", "/api/v1/mood/today"): InteractionType.MOOD_ENTRY,
            ("POST", "/api/v1/mood/"): InteractionType.MOOD_ENTRY,
            ("PUT", "/api/v1/mood/today"): InteractionType.MOOD_ENTRY,
            
            # Journal
            ("POST", "/api/v1/journal/entries"): InteractionType.JOURNAL_ENTRY,
            ("PUT", "/api/v1/journal/entries/{entry_id}"): InteractionType.JOURNAL_ENTRY,
            ("POST", "/api/v1/journal/collections"): InteractionType.JOURNAL_ENTRY,
            
            # Study sessions
            ("POST", "/api/v1/study/sets"): InteractionType.STUDY_SESSION,
            ("POST", "/api/v1/study/sets/{set_id}/cards"): InteractionType.STUDY_SESSION,
            
            # Calendar interactions
            ("POST", "/api/v1/calendar/entries"): InteractionType.CALENDAR_ENTRY,
            ("PUT", "/api/v1/calendar/entries/{date}"): InteractionType.CALENDAR_ENTRY,
            
            # Gratitude
            ("POST", "/api/v1/journal/gratitude"): InteractionType.GRATITUDE_ENTRY,
            
            # Profile and settings
            ("PUT", "/api/v1/user/me"): InteractionType.PROFILE_UPDATE,
            ("PUT", "/api/v1/user/me/profile"): InteractionType.PROFILE_UPDATE,
            ("PATCH", "/api/v1/user/profile"): InteractionType.PROFILE_UPDATE,
            ("PUT", "/api/v1/user/profile"): InteractionType.PROFILE_UPDATE,
            ("PUT", "/api/v1/user/avatar"): InteractionType.PROFILE_UPDATE,
            ("PUT", "/api/v1/time/timezone"): InteractionType.SETTINGS_CHANGE,
        }
        
        # Endpoints to exclude from tracking (read-only operations)
        self.excluded_patterns = [
            "/api/v1/user/me/export",
            "/api/v1/user/me/activity",
            "/api/v1/auth/",
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/metrics"
        ]
        
        # Pattern matching for dynamic routes
        self.dynamic_patterns = {
            "habit_completion": [
                ("POST", "/api/v1/habits/{}/complete"),
                ("PUT", "/api/v1/habits/{}/complete/{}"),
            ],
            "goal_progress": [
                ("PUT", "/api/v1/goals/{}/increment"),
                ("PUT", "/api/v1/goals/{}/complete"),
                ("PUT", "/api/v1/goals/{}/progress"),
            ],
            "journal_entry": [
                ("PUT", "/api/v1/journal/entries/{}"),
                ("POST", "/api/v1/journal/collections/{}/entries"),
            ],
            "study_session": [
                ("POST", "/api/v1/study/sets/{}/cards"),
                ("PUT", "/api/v1/study/sets/{}/cards/{}"),
            ],
            "calendar_entry": [
                ("PUT", "/api/v1/calendar/entries/{}"),
            ]
        }
    
    async def dispatch(self, request: Request, call_next):
        """Process request and track interactions if applicable"""
        
        # Skip non-meaningful requests
        if not self._should_track_request(request):
            return await call_next(request)
        
        # Process the request first
        response = await call_next(request)
        
        # Only track successful operations
        if response.status_code >= 400:
            return response
        
        # Track interaction asynchronously (don't block response)
        asyncio.create_task(self._track_interaction_async(request, response))
        
        return response
    
    def _should_track_request(self, request: Request) -> bool:
        """Determine if request should be tracked for streaks"""
        
        # Skip OPTIONS requests
        if request.method == "OPTIONS":
            return False
        
        # Skip excluded endpoints
        path = request.url.path
        for excluded in self.excluded_patterns:
            if excluded in path:
                return False
        
        # Only track meaningful HTTP methods
        if request.method not in ["POST", "PUT", "PATCH"]:
            return False
        
        # Skip if no Authorization header (not authenticated)
        if not request.headers.get("Authorization"):
            return False
        
        return True
    
    def _get_interaction_type(self, request: Request) -> Optional[InteractionType]:
        """Determine interaction type based on endpoint"""
        method = request.method
        path = request.url.path
        
        # Check exact matches first
        if (method, path) in self.interaction_mapping:
            return self.interaction_mapping[(method, path)]
        
        # Check dynamic patterns
        for interaction_type_name, patterns in self.dynamic_patterns.items():
            for pattern_method, pattern_path in patterns:
                if method == pattern_method and self._matches_pattern(path, pattern_path):
                    return getattr(InteractionType, interaction_type_name.upper())
        
        # Default fallback for certain endpoints
        if "pomodoro" in path.lower():
            return InteractionType.POMODORO_SESSION
        elif "meditation" in path.lower():
            return InteractionType.MEDITATION_SESSION
        
        return None
    
    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern with {} placeholders"""
        pattern_parts = pattern.split("/")
        path_parts = path.split("/")
        
        if len(pattern_parts) != len(path_parts):
            return False
        
        for pattern_part, path_part in zip(pattern_parts, path_parts):
            if pattern_part == "{}":
                continue  # Wildcard match
            elif pattern_part != path_part:
                return False
        
        return True
    
    async def _track_interaction_async(self, request: Request, response: Response):
        """Track interaction asynchronously to avoid blocking response"""
        try:
            async with async_session() as db:
                # Get user from token
                user = await self._get_user_from_request(request, db)
                if not user:
                    return
                
                # Determine interaction type
                interaction_type = self._get_interaction_type(request)
                if not interaction_type:
                    return
                
                # Extract metadata from request
                metadata = self._extract_metadata(request, response)
                
                # Record the interaction
                await daily_streak_service.record_interaction(
                    db, user, interaction_type, metadata
                )
                
                logger.debug(f"Tracked {interaction_type.value} for user {user.id}")
                
        except Exception as e:
            # Don't let tracking errors affect the main application
            logger.warning(f"Failed to track interaction: {str(e)}")
    
    async def _get_user_from_request(self, request: Request, db: AsyncSession):
        """Get user from authentication token"""
        try:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None
            
            token = auth_header.split(" ")[1]
            user = await get_current_user_from_token(token, db)
            return user
            
        except Exception:
            return None
    
    def _extract_metadata(self, request: Request, response: Response) -> Dict[str, Any]:
        """Extract relevant metadata from request/response"""
        metadata = {
            "endpoint": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "user_agent": request.headers.get("user-agent", "unknown")[:100],
        }
        
        # Add request-specific metadata
        if hasattr(request.state, "start_time"):
            metadata["response_time_ms"] = round((time.time() - request.state.start_time) * 1000, 2)
        
        return metadata 