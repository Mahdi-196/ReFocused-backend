from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class HabitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    is_favorite: Optional[bool] = False

class HabitCreate(HabitBase):
    pass

class HabitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_favorite: Optional[bool] = None

class HabitResponse(HabitBase):
    id: int
    streak: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True

class HabitCompletionBase(BaseModel):
    habit_id: int
    completed: bool = False

class HabitCompletionCreate(HabitCompletionBase):
    date: date

class HabitCompletionResponse(HabitCompletionBase):
    id: int
    date: date
    created_at: datetime
    
    class Config:
        from_attributes = True 