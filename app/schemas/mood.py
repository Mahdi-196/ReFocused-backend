from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class MoodBase(BaseModel):
    happiness: int = Field(..., ge=1, le=5, description="Happiness level from 1-5")
    satisfaction: int = Field(..., ge=1, le=5, description="Satisfaction level from 1-5") 
    stress: int = Field(..., ge=1, le=5, description="Stress level from 1-5")
    day_rating: int = Field(..., ge=1, le=10, description="Overall day rating from 1-10")
    note: Optional[str] = Field(None, max_length=1000)

class MoodCreate(MoodBase):
    date: date

class MoodUpdate(BaseModel):
    happiness: Optional[int] = Field(None, ge=1, le=5)
    satisfaction: Optional[int] = Field(None, ge=1, le=5)
    stress: Optional[int] = Field(None, ge=1, le=5)
    day_rating: Optional[int] = Field(None, ge=1, le=10)
    note: Optional[str] = Field(None, max_length=1000)

class MoodResponse(MoodBase):
    id: int
    date: date
    created_at: datetime
    
    class Config:
        from_attributes = True 