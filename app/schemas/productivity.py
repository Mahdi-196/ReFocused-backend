from datetime import datetime, date
from typing import Dict, List, Optional, Any
from decimal import Decimal
from pydantic import BaseModel, Field, validator
from enum import Enum

class ActivityType(str, Enum):
    POMODORO = "pomodoro"
    MEDITATION = "meditation"
    BREATHING = "breathing"
    JOURNAL = "journal"
    GRATITUDE = "gratitude"
    HABIT = "habit"
    GOAL = "goal"

class ActivityLogRequest(BaseModel):
    activity_type: ActivityType
    activity_data: Dict[str, Any]
    session_id: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None

class PomodoroSessionRequest(BaseModel):
    duration_minutes: int = Field(..., ge=1, le=120)
    completed: bool = True
    interruptions: int = Field(0, ge=0)
    session_id: Optional[str] = None

class MeditationSessionRequest(BaseModel):
    duration_minutes: int = Field(..., ge=1, le=120)
    meditation_type: str = Field("mindfulness", max_length=50)
    completed: bool = True
    session_id: Optional[str] = None

class BreathingExerciseRequest(BaseModel):
    duration_minutes: int = Field(..., ge=1, le=60)
    exercise_type: str = Field("4-7-8", max_length=50)
    completed: bool = True
    session_id: Optional[str] = None

class JournalEntryRequest(BaseModel):
    entry_id: int = Field(..., gt=0)
    word_count: int = Field(..., ge=0)
    time_spent_minutes: int = Field(..., ge=0)
    session_id: Optional[str] = None

class GratitudeEntryRequest(BaseModel):
    entry_id: int = Field(..., gt=0)
    character_count: int = Field(..., ge=0)
    session_id: Optional[str] = None

class HabitCompletionRequest(BaseModel):
    habit_id: int = Field(..., gt=0)
    completion_time: datetime
    session_id: Optional[str] = None

class GoalCompletionRequest(BaseModel):
    goal_id: int = Field(..., gt=0)
    goal_type: str = Field(..., max_length=50)
    progress_percentage: float = Field(..., ge=0, le=100)
    session_id: Optional[str] = None

class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    activity_type: str
    activity_data: Dict[str, Any]
    quality_score: float
    date: date
    timestamp: datetime
    session_id: Optional[str]
    device_info: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True

class MonthlyTargetsRequest(BaseModel):
    target_app_days: int = Field(20, ge=1, le=31)
    target_pomodoro_hours: float = Field(12.0, ge=0, le=100)
    target_meditation_sessions: int = Field(4, ge=0, le=100)
    target_journal_entries: int = Field(8, ge=0, le=100)
    target_habit_count: int = Field(3, ge=0, le=20)
    target_habit_completion_rate: float = Field(80.0, ge=0, le=100)

class MonthlyTargetsResponse(BaseModel):
    id: int
    user_id: int
    target_app_days: int
    target_pomodoro_hours: float
    target_meditation_sessions: int
    target_journal_entries: int
    target_habit_count: int
    target_habit_completion_rate: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ScoreBreakdown(BaseModel):
    goals_points: float
    habits_points: float
    focus_points: float
    wellness_points: float
    consistency_multiplier: float

class MonthlyProductivityScoreResponse(BaseModel):
    user_id: int
    year: int
    month: int
    score: float
    tier: int
    breakdown: ScoreBreakdown
    calculation_data: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MonthlyScoreRequest(BaseModel):
    year: int = Field(..., ge=2024, le=2030)
    month: int = Field(..., ge=1, le=12)
    force_recalculate: bool = False

class ActivitySummaryResponse(BaseModel):
    total_activities: int
    by_type: Dict[str, Dict[str, Any]]
    by_date: Dict[str, Dict[str, Any]]
    quality_metrics: Dict[str, float]

class TierInfo(BaseModel):
    tier: int
    name: str
    description: str
    min_score: float
    max_score: float
    requirements: List[str]

class ProductivityInsightsResponse(BaseModel):
    current_month: MonthlyProductivityScoreResponse
    tier_info: TierInfo
    improvement_suggestions: List[str]
    strengths: List[str]
    next_tier_requirements: Optional[List[str]]

class MonthlyTrendsResponse(BaseModel):
    months: List[str]
    scores: List[float]
    tiers: List[int]
    breakdown_trends: Dict[str, List[float]]

class ProductivityAnalyticsResponse(BaseModel):
    engagement_days: int
    total_activities: int
    quality_score_average: float
    most_active_activity_type: str
    streak_days: int
    improvement_areas: List[str]

class RecalculateScoreRequest(BaseModel):
    year: int = Field(..., ge=2024, le=2030)
    month: int = Field(..., ge=1, le=12)
    user_id: Optional[int] = None  # For admin use

class BulkActivityLogRequest(BaseModel):
    activities: List[ActivityLogRequest] = Field(..., max_items=100)

class BulkActivityLogResponse(BaseModel):
    success_count: int
    failed_count: int
    successful_activities: List[ActivityLogResponse]
    failed_activities: List[Dict[str, Any]]

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    
class ErrorResponse(BaseModel):
    error: str
    message: str
    timestamp: datetime

# Validation helpers
def validate_month_year(year: int, month: int) -> bool:
    """Validate year and month combination."""
    if not (2024 <= year <= 2030):
        return False
    if not (1 <= month <= 12):
        return False
    return True

# Custom validators
class MonthlyScoreRequestValidator(BaseModel):
    year: int
    month: int
    force_recalculate: bool = False

    @validator('year')
    def validate_year(cls, v):
        if not (2024 <= v <= 2030):
            raise ValueError('Year must be between 2024 and 2030')
        return v

    @validator('month')
    def validate_month(cls, v):
        if not (1 <= v <= 12):
            raise ValueError('Month must be between 1 and 12')
        return v