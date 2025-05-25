from passlib.context import CryptContext
from jose import JWTError, jwt, ExpiredSignatureError
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import time

from app.db.database import get_db
from app.db.models import User
from app.core.config import settings

# Password hashing settings with stronger configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# JWT settings from config
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# OAuth2 token URL that matches the router
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None
    exp: Optional[datetime] = None

def verify_password(plain_password, hashed_password):
    """Verify that a plain password matches the hashed password."""
    # Use constant-time comparison to prevent timing attacks
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Generate a hash for a password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token with security enhancements."""
    to_encode = data.copy()
    
    # Ensure required claims are present
    if "sub" not in to_encode:
        raise ValueError("Missing subject claim in token data")
    
    # Add standard JWT claims
    iat = datetime.utcnow()
    to_encode.update({"iat": iat})  # Issued at time
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode.update({"exp": expire})  # Expiration time
    to_encode.update({"nbf": iat})     # Not valid before issued time
    
    # Add JWT ID for token tracking/revocation if needed
    to_encode.update({"jti": str(int(time.time()))})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt

def decode_token(token: str) -> TokenData:
    """Decode a JWT token and return the token data with enhanced validation."""
    try:
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM],
            options={"verify_signature": True, "verify_exp": True, "verify_nbf": True}
        )
        
        email: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        exp: datetime = datetime.fromtimestamp(payload.get("exp"))
        
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject claim",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        token_data = TokenData(email=email, user_id=user_id, exp=exp)
        return token_data
        
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Get the current user from the token with enhanced security."""
    token_data = decode_token(token)
    
    # More efficient query using user_id if available
    if token_data.user_id:
        user = db.query(User).filter(User.id == token_data.user_id).first()
    else:
        user = db.query(User).filter(User.email == token_data.email).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    """Get the current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user 