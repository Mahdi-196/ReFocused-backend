from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class MoodBase(BaseModel):
    happiness: int = Field(..., ge=1, le=5, description="Happiness level from 1-5")
    satisfaction: int = Field(..., ge=1, le=5, description="Satisfaction level from 1-5") 
    stress: int = Field(..., ge=1, le=5, description="Stress level from 1-5")

class MoodCreate(MoodBase):
    date: date

class MoodUpdate(BaseModel):
    happiness: Optional[int] = Field(None, ge=1, le=5)
    satisfaction: Optional[int] = Field(None, ge=1, le=5)
    stress: Optional[int] = Field(None, ge=1, le=5)

# Response schema that includes all database fields but makes optional ones optional
class MoodResponse(BaseModel):
    id: int
    user_id: int
    date: date
    happiness: int
    satisfaction: int
    stress: int
    dayRating: Optional[int] = Field(None, ge=1, le=10, description="Overall day rating from 1-10", alias="day_rating")
    notes: Optional[str] = Field(None, max_length=1000, description="Optional note", alias="note")
    createdAt: datetime = Field(alias="created_at")
    updatedAt: Optional[datetime] = Field(None, alias="updated_at")
    
    class Config:
        from_attributes = True
        populate_by_name = True

# Full mood schema for internal use (includes day_rating and note)
class MoodFull(MoodBase):
    day_rating: Optional[int] = Field(None, ge=1, le=10, description="Overall day rating from 1-10")
    note: Optional[str] = Field(None, max_length=1000)
    date: date 