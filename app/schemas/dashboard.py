from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date
from .habit import HabitCompletionResponse
from .mood import MoodResponse

class DailyEntryResponse(BaseModel):
    date: date
    mood: Optional[MoodResponse] = None
    habit_completions: List[HabitCompletionResponse] = []
    
    class Config:
        from_attributes = True

class DailyEntryCreate(BaseModel):
    date: date
    happiness: Optional[int] = None
    focus: Optional[int] = None
    stress: Optional[int] = None
    day_rating: Optional[int] = None
    note: Optional[str] = None
    habit_completions: List[dict] = []  # [{"habit_id": 1, "completed": true}]
    
    class Config:
        populate_by_name = True 