from typing import Optional
from pydantic import BaseModel, EmailStr, constr
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    is_active: Optional[bool] = True

class UserCreate(UserBase):
    password: constr(min_length=8, max_length=128)

class UserUpdate(UserBase):
    password: Optional[constr(min_length=8, max_length=128)] = None

class UserResponse(UserBase):
    id: int
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserInDB(UserResponse):
    hashed_password: str
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None

    class Config:
        from_attributes = True 