from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
from enum import Enum


class PriorityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class GoalBase(BaseModel):
    """Base schema for Goal with common fields."""
    title: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    priority: PriorityEnum = PriorityEnum.medium
    category: Optional[str] = None
    
    @validator('title')
    def title_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()


class GoalCreate(GoalBase):
    """Schema for creating a new goal."""


class GoalUpdate(BaseModel):
    """Schema for updating an existing goal."""
    title: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    is_completed: Optional[bool] = None
    priority: Optional[PriorityEnum] = None
    category: Optional[str] = None
    
    @validator('title', pre=True, always=True)
    def title_must_not_be_empty_if_provided(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Title cannot be empty if provided')
        return v.strip() if v else v


class Goal(GoalBase):
    """Schema for Goal response."""
    id: int
    is_completed: bool
    user_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True 