from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date
from .habit import HabitCompletionResponse
from .mood import MoodResponse
from .journal import Gratitude  # Add gratitude import

class DailyEntryResponse(BaseModel):
    date: date
    mood: Optional[MoodResponse] = None
    habit_completions: List[HabitCompletionResponse] = []
    gratitudes: List[Gratitude] = []  # Add gratitudes field
    
    class Config:
        from_attributes = True

class DailyEntryCreate(BaseModel):
    """Schema for creating daily entries with mood and habit data.
    
    Note: day_rating field is deprecated and will be ignored (removed from mood model).
    Use happiness, focus, and stress fields for mood tracking.
    """
    date: date
    happiness: Optional[int] = Field(None, ge=1, le=5, description="Happiness level from 1-5")
    focus: Optional[int] = Field(None, ge=1, le=5, description="Focus level from 1-5") 
    stress: Optional[int] = Field(None, ge=1, le=5, description="Stress level from 1-5")
    
    # Deprecated fields - kept for backward compatibility but ignored
    day_rating: Optional[int] = Field(None, ge=1, le=10, description="DEPRECATED: Overall day rating (ignored - use happiness/focus/stress instead)")
    note: Optional[str] = Field(None, description="DEPRECATED: Note field (ignored - use separate note endpoints)")
    
    habit_completions: List[dict] = Field(default=[], description="List of habit completions: [{'habit_id': 1, 'completed': true}]")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "date": "2024-01-15",
                "happiness": 4,
                "focus": 3,
                "stress": 2,
                "habit_completions": [
                    {"habit_id": 1, "completed": True},
                    {"habit_id": 2, "completed": False}
                ]
            }
        } 