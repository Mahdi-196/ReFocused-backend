from typing import Optional
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[int] = None
    exp: Optional[int] = None
    type: Optional[str] = None

class TokenResponse(BaseModel):
    """OAuth2 token response schema"""
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    scope: Optional[str] = None 