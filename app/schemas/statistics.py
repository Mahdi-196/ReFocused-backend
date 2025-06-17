from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

# Request schemas
class FocusTimeUpdate(BaseModel):
    seconds: int = Field(..., ge=0, description="Focus time in seconds to add")

class SessionsUpdate(BaseModel):
    increment: int = Field(..., ge=0, description="Number of completed sessions to add")

class TasksUpdate(BaseModel):
    increment: int = Field(..., ge=0, description="Number of completed tasks to add")

class StatisticsFilter(BaseModel):
    filter: str = Field("D", description="Filter period: D (daily), W (weekly), M (monthly)")

# Response schemas - Updated to match frontend expectations
class StatisticsResponse(BaseModel):
    focusTime: int = Field(..., alias="focus_time", description="Total focus time in seconds")
    sessions: int = Field(..., description="Total number of completed sessions")
    tasksDone: int = Field(..., alias="tasks_done", description="Total number of completed tasks")

    class Config:
        from_attributes = True
        populate_by_name = True

# Optional detailed response with daily breakdown
class DailyStatistics(BaseModel):
    date: date
    focusTime: int = Field(..., alias="focus_time")
    sessions: int
    tasksDone: int = Field(..., alias="tasks_done")
    
    class Config:
        populate_by_name = True

class DetailedStatisticsResponse(BaseModel):
    summary: StatisticsResponse
    daily: list[DailyStatistics] = [] 