from pydantic import BaseModel, Field, validator
from typing import Optional
import re


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Star rating 1-5")
    category: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=5000)
    email: Optional[str] = Field(None)

    @validator('email')
    def validate_email(cls, v):
        if v is not None:
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
                raise ValueError('Invalid email format')
            return v.lower().strip()
        return v

    @validator('category')
    def strip_category(cls, v: str) -> str:
        return v.strip()

    @validator('message')
    def strip_message(cls, v: str) -> str:
        return v.strip()


class FeedbackResponse(BaseModel):
    status: str
    feedbackId: Optional[str] = None
    message: Optional[str] = None


