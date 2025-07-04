from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class GoalTypeEnum(str, Enum):
    """Goal type enumeration for the three supported goal types."""
    percentage = "percentage"  # 0-100% progress
    counter = "counter"       # Point system with target number 2-999
    checklist = "checklist"   # One-time check off


class GoalDurationEnum(str, Enum):
    """Goal duration enumeration for the two supported duration types."""
    two_week = "two_week"       # 2-week goals with expiration  
    long_term = "long_term"     # Long-term goals without expiration
    
    @classmethod
    def _missing_(cls, value):
        """Handle legacy and alternative enum values for backwards compatibility."""
        # Map legacy database values to proper enum members
        legacy_mapping = {
            "2_week": cls.two_week,
            "2week": cls.two_week,
        }
        return legacy_mapping.get(value)


class GoalBase(BaseModel):
    """Base schema for Goal with common fields."""
    name: str = Field(..., min_length=1, max_length=255)
    goal_type: GoalTypeEnum
    duration: GoalDurationEnum
    target_value: Optional[int] = Field(None, ge=1, le=999)
    
    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Goal name cannot be empty')
        return v.strip()
    
    @validator('target_value')
    def validate_target_value(cls, v, values):
        goal_type = values.get('goal_type')
        
        if goal_type == GoalTypeEnum.percentage:
            # Percentage goals always have target of 100
            if v is not None and v != 100:
                raise ValueError('Percentage goals must have target_value of 100 or None (auto-set to 100)')
            return 100
        elif goal_type == GoalTypeEnum.counter:
            # Counter goals need target between 2-999
            if v is None:
                raise ValueError('Counter goals must specify target_value between 2-999')
            if v < 2 or v > 999:
                raise ValueError('Counter goal target_value must be between 2-999')
            return v
        elif goal_type == GoalTypeEnum.checklist:
            # Checklist goals always have target of 1
            if v is not None and v != 1:
                raise ValueError('Checklist goals must have target_value of 1 or None (auto-set to 1)')
            return 1
        
        return v


class GoalCreate(GoalBase):
    """Schema for creating a new goal."""
    pass


class GoalUpdate(BaseModel):
    """Schema for updating an existing goal."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    current_value: Optional[int] = Field(None, ge=0)
    
    @validator('name')
    def name_must_not_be_empty_if_provided(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Goal name cannot be empty if provided')
        return v.strip() if v else v


class GoalProgressUpdate(BaseModel):
    """Schema for updating goal progress."""
    increment: Optional[int] = Field(None, ge=1)  # For counter goals - how much to add
    new_value: Optional[int] = Field(None, ge=0)  # Direct value update
    complete: Optional[bool] = None  # For checklist goals - mark as complete/incomplete
    
    @validator('new_value')
    def validate_new_value(cls, v):
        if v is not None and v < 0:
            raise ValueError('Goal progress cannot be negative')
        return v


class Goal(BaseModel):
    """Schema for Goal response."""
    id: int
    name: str
    goal_type: GoalTypeEnum
    duration: GoalDurationEnum
    target_value: int
    current_value: int
    is_completed: bool
    progress_percentage: float  # Calculated field: (current_value / target_value) * 100
    expires_at: Optional[datetime] = None  # Only for 2_week goals
    user_id: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None  # Set when goal is completed
    
    class Config:
        from_attributes = True


class GoalStats(BaseModel):
    """Schema for goal statistics."""
    total_goals: int
    completed_goals: int
    percentage_goals: int
    counter_goals: int
    checklist_goals: int
    active_2_week_goals: int  # Non-expired, non-completed 2-week goals
    long_term_goals: int      # All long-term goals
    completion_rate: float    # Percentage of completed goals 


# New schemas for Goals Completion History system

class GoalHistoryEntry(BaseModel):
    """Schema for individual goal in history response."""
    id: int
    name: str
    goal_type: str  # String value instead of enum
    duration: str   # String value instead of enum
    target_value: int
    current_value: int
    completed_at: str  # ISO datetime string for frontend
    completion_days: int  # Days between created_at and completed_at (minimum 1)
    created_at: str    # ISO datetime string for frontend
    
    class Config:
        from_attributes = True


class GoalsHistoryResponse(BaseModel):
    """Schema for goals history endpoint response."""
    goals: List[GoalHistoryEntry]
    total_count: int
    date_range: Dict[str, str]  # {"start": ISO string, "end": ISO string}
    
    class Config:
        from_attributes = True


class CompletionByType(BaseModel):
    """Schema for completion statistics by goal type."""
    percentage: int = 0
    counter: int = 0
    checklist: int = 0


class CompletionByDuration(BaseModel):
    """Schema for completion statistics by duration."""
    two_week: int = 0
    long_term: int = 0


class CompletionStatsResponse(BaseModel):
    """Schema for completion statistics endpoint response."""
    total_completed: int
    avg_completion_days: float
    completion_rate: float  # Percentage of created goals that were completed
    by_type: CompletionByType
    by_duration: CompletionByDuration
    
    class Config:
        from_attributes = True 