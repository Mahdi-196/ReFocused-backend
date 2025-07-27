from typing import Optional, List
from pydantic import BaseModel, Field, validator
from datetime import datetime, date
from .journal import Gratitude  # Add gratitude import

# Calendar Habit Completion schemas
class CalendarHabitCompletionBase(BaseModel):
    habit_id: int
    habit_name: str = Field(..., min_length=1, max_length=255)
    completed: bool = False
    completed_at: Optional[datetime] = None
    was_active_on_date: bool = True

class CalendarHabitCompletionCreate(CalendarHabitCompletionBase):
    pass

class CalendarHabitCompletionUpdate(BaseModel):
    completed: Optional[bool] = None
    completed_at: Optional[datetime] = None

class CalendarHabitCompletionResponse(CalendarHabitCompletionBase):
    id: int
    calendar_entry_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Calendar Mood Entry schemas
class CalendarMoodEntryBase(BaseModel):
    happiness: int = Field(..., ge=1, le=5, description="Happiness level from 1-5")
    focus: int = Field(..., ge=1, le=5, description="Focus level from 1-5")
    stress: int = Field(..., ge=1, le=5, description="Stress level from 1-5")
    day_rating: Optional[int] = Field(None, ge=1, le=10, description="Overall day rating from 1-10")

class CalendarMoodEntryCreate(CalendarMoodEntryBase):
    pass

class CalendarMoodEntryUpdate(BaseModel):
    happiness: Optional[int] = Field(None, ge=1, le=5)
    focus: Optional[int] = Field(None, ge=1, le=5)
    stress: Optional[int] = Field(None, ge=1, le=5)
    day_rating: Optional[int] = Field(None, ge=1, le=10)

class CalendarMoodEntryResponse(CalendarMoodEntryBase):
    id: int
    calendar_entry_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Calendar Entry schemas
class CalendarEntryBase(BaseModel):
    date: date
    notes: Optional[str] = Field(None, max_length=1000)

class CalendarEntryCreate(CalendarEntryBase):
    habit_completions: Optional[List[CalendarHabitCompletionCreate]] = []
    mood_entry: Optional[CalendarMoodEntryCreate] = None
    
    @validator('date')
    def validate_date_format(cls, v):
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError('Date must be in YYYY-MM-DD format')
        return v

class CalendarEntryUpdate(BaseModel):
    notes: Optional[str] = Field(None, max_length=1000)
    habit_completions: Optional[List[CalendarHabitCompletionCreate]] = None
    mood_entry: Optional[CalendarMoodEntryCreate] = None

class CalendarEntryResponse(CalendarEntryBase):
    id: int
    user_id: int
    is_locked: bool = False
    habit_completions: List[CalendarHabitCompletionResponse] = []
    mood_entry: Optional[CalendarMoodEntryResponse] = None
    gratitudes: List[Gratitude] = []  # Add gratitudes field
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Bulk operations schemas
class CalendarEntriesRangeRequest(BaseModel):
    start_date: date
    end_date: date
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('end_date must be after start_date')
        if 'start_date' in values and (v - values['start_date']).days > 365:
            raise ValueError('Date range cannot exceed 365 days')
        return v

class CalendarEntriesRangeResponse(BaseModel):
    entries: List[CalendarEntryResponse]
    start_date: date
    end_date: date
    total_entries: int

# Error responses
class CalendarError(BaseModel):
    detail: str
    code: str

class ReadOnlyError(CalendarError):
    code: str = "CALENDAR_READ_ONLY"
    detail: str = "Cannot modify calendar entries for past dates" 