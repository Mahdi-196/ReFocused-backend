from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    is_active: Optional[bool] = True

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

class UserUpdate(UserBase):
    password: Optional[str] = Field(None, min_length=8, max_length=128)

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserProfile(BaseModel):
    """Schema for user profile responses with basic user information."""
    id: int
    email: str
    name: Optional[str] = None
    profile_picture: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

class UserInDB(UserResponse):
    hashed_password: str
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None

    class Config:
        from_attributes = True 

class AccountDeleteRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=128) 