from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class MoodBase(BaseModel):
    happiness: int = Field(..., ge=1, le=5, description="Happiness level from 1-5")
    focus: int = Field(..., ge=1, le=5, description="Focus level from 1-5")
    stress: int = Field(..., ge=1, le=5, description="Stress level from 1-5")

class MoodCreate(MoodBase):
    date: date

class MoodUpdate(BaseModel):
    happiness: Optional[int] = Field(None, ge=1, le=5)
    focus: Optional[int] = Field(None, ge=1, le=5)
    stress: Optional[int] = Field(None, ge=1, le=5)

class TodayMoodCreate(MoodBase):
    """Schema for creating today's mood entry (no date required)"""
    pass

class TodayMoodUpdate(BaseModel):
    """Schema for updating today's mood entry"""
    happiness: Optional[int] = Field(None, ge=1, le=5)
    focus: Optional[int] = Field(None, ge=1, le=5)
    stress: Optional[int] = Field(None, ge=1, le=5)

# Response schema that includes all database fields
class MoodResponse(BaseModel):
    id: int
    user_id: int
    date: date
    happiness: int
    focus: int
    stress: int
    createdAt: datetime = Field(alias="created_at")
    updatedAt: Optional[datetime] = Field(None, alias="updated_at")
    
    class Config:
        from_attributes = True
        populate_by_name = True

# Full mood schema for internal use
class MoodFull(MoodBase):
    date: date 