from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from app.core.config import settings

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

class AvatarConfig(BaseModel):
    """Schema for avatar configuration data."""
    style: str = Field(..., description="Avatar style (e.g., 'open-peeps', 'adventurer', 'lorelei')")
    seed: str = Field(..., description="Unique seed/identifier for the avatar")
    options: Optional[Dict[str, Any]] = Field(default=None, description="Additional avatar options/customizations")
    
    class Config:
        json_schema_extra = {
            "example": {
                "style": "open-peeps",
                "seed": "user123_avatar",
                "options": {
                    "accessory": "glasses",
                    "clothing": "shirt"
                }
            }
        }

class AvatarUpdateRequest(BaseModel):
    """Schema for updating user avatar."""
    avatar_config: AvatarConfig
    avatar_url: Optional[str] = Field(default=None, description="Generated avatar URL (optional)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "avatar_config": {
                    "style": "open-peeps",
                    "seed": "user123_avatar",
                    "options": {}
                },
                "avatar_url": f"{settings.DICEBEAR_API_BASE_URL}/7.x/open-peeps/svg?seed=user123_avatar"
            }
        }

class AvatarResponse(BaseModel):
    """Schema for avatar response."""
    success: bool
    message: str
    avatar_url: Optional[str] = None
    avatar_config: Optional[AvatarConfig] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Avatar updated successfully",
                "avatar_url": f"{settings.DICEBEAR_API_BASE_URL}/7.x/open-peeps/svg?seed=user123_avatar",
                "avatar_config": {
                    "style": "open-peeps", 
                    "seed": "user123_avatar",
                    "options": {}
                }
            }
        } 

class ProfileUpdate(BaseModel):
    """Schema for profile update requests."""
    name: Optional[str] = None
    profile_picture: Optional[str] = None
    avatar: Optional[str] = None  # Legacy support for frontend compatibility

class ChangePasswordRequest(BaseModel):
    """Schema for password change requests."""
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    
class ChangePasswordResponse(BaseModel):
    """Schema for password change response."""
    success: bool
    message: str


class ChangeUsernameRequest(BaseModel):
    """Schema for username/name change requests."""
    new_name: str = Field(..., min_length=1, max_length=100)


class ChangeUsernameResponse(BaseModel):
    """Schema for username/name change response."""
    success: bool
    message: str
    name: str 