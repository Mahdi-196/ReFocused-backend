from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Star rating 1-5")
    category: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=5000)
    email: Optional[EmailStr] = Field(None)

    @field_validator('category')
    def strip_category(cls, v: str) -> str:
        return v.strip()

    @field_validator('message')
    def strip_message(cls, v: str) -> str:
        return v.strip()


class FeedbackResponse(BaseModel):
    status: str
    feedbackId: Optional[str] = None
    message: Optional[str] = None


