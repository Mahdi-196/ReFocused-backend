from pydantic import BaseModel, validator
from typing import Optional

class GoogleAuthRequest(BaseModel):
    """Request model for Google OAuth authentication."""
    token: str
    
    @validator('token')
    def validate_token(cls, v):
        if not v or not v.strip():
            raise ValueError('Token cannot be empty')
        return v.strip()

class UserResponse(BaseModel):
    """User information in response."""
    id: int
    email: str
    name: str
    username: Optional[str] = None
    profile_picture: Optional[str] = None
    
    class Config:
        from_attributes = True

class GoogleAuthResponse(BaseModel):
    """Response model for Google OAuth authentication."""
    access_token: str
    user: UserResponse
    token_type: str = "bearer"
    expires_in: int 