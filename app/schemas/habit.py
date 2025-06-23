from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, date

class HabitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    is_favorite: Optional[bool] = False

class HabitCreate(HabitBase):
    is_active: Optional[bool] = True

class HabitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_favorite: Optional[bool] = None
    is_active: Optional[bool] = None

class HabitResponse(HabitBase):
    id: int
    streak: int = 0
    is_active: bool = True
    created_at: datetime
    last_updated_utc: datetime
    last_completed_date: Optional[str] = None  # YYYY-MM-DD format in user's timezone
    
    model_config = ConfigDict(from_attributes=True)

class HabitCompletionBase(BaseModel):
    habit_id: int = Field(alias="habitId")
    date: date
    completed: bool = True

class HabitCompletionCreate(HabitCompletionBase):
    timezone: str

class HabitCompletionUpdate(BaseModel):
    habit_id: int = Field(alias="habitId")
    date: date
    completed: bool

    model_config = ConfigDict(populate_by_name=True)

class HabitCompletionResponse(BaseModel):
    id: int
    habit_id: int
    date: date
    completed: bool
    completed_at: Optional[str] = None  # ISO timestamp string
    timezone: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class HabitStatsResponse(BaseModel):
    habit_id: int
    total_completions: int
    current_streak: int
    longest_streak: int
    completion_rate_7days: float
    completion_rate_30days: float
    last_completed: Optional[date] = None

class BulkCompletionRequest(BaseModel):
    completions: List[HabitCompletionUpdate]

class BulkCompletionResponse(BaseModel):
    success_count: int
    error_count: int
    errors: List[str] = [] 