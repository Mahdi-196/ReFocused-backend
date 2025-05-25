from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt, ExpiredSignatureError
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import logging
from app.core.config import settings
from app.core.security_config import security_config
from app.db.database import get_db
from app.db.models import User, TokenBlacklist, LoginAttempt
from app.utils.security import generate_secure_random_string

logger = logging.getLogger("auth")

# Using bcrypt with enhanced security
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

class TokenManager:
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        # Create JWT token with some extra security stuff
        to_encode = data.copy()
        
        # Add standard JWT stuff
        iat = datetime.utcnow()
        to_encode.update({
            "iat": iat,  # When issued
            "nbf": iat,  # Not valid before
            "jti": generate_secure_random_string(32),  # Unique ID
            "type": "access"  # Token type
        })
        
        # Set when it expires
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        

        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        # Create refresh token
        to_encode = data.copy()
        
        # Add refresh token specific claims
        iat = datetime.utcnow()
        to_encode.update({
            "iat": iat,
            "nbf": iat,
            "jti": generate_secure_random_string(32),
            "type": "refresh",
            "exp": datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        })
        

        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str, db: Session) -> Dict[str, Any]:
        """Verify a token with enhanced security checks."""
        try:
            # Check if token is blacklisted
            if TokenBlacklist.is_blacklisted(db, token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Decode token with enhanced validation
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "require": ["exp", "iat", "nbf", "jti", "type"]
                }
            )
            
            return payload
            
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

class AuthenticationManager:
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Generate a secure password hash."""
        return pwd_context.hash(password)
    
    @staticmethod
    def validate_password_strength(password: str) -> bool:
        """Validate password strength against security requirements."""
        if len(password) < security_config.PASSWORD_MIN_LENGTH:
            return False
        if len(password) > security_config.PASSWORD_MAX_LENGTH:
            return False
        if security_config.PASSWORD_REQUIRE_UPPER and not any(c.isupper() for c in password):
            return False
        if security_config.PASSWORD_REQUIRE_LOWER and not any(c.islower() for c in password):
            return False
        if security_config.PASSWORD_REQUIRE_NUMBER and not any(c.isdigit() for c in password):
            return False
        if security_config.PASSWORD_REQUIRE_SPECIAL and not any(c in "!@#$%^&*(),.?\":{}|<>" for c in password):
            return False
        return True
    
    @staticmethod
    def check_login_attempts(db: Session, user_id: int) -> bool:
        """Check if user has exceeded maximum login attempts."""
        attempts = LoginAttempt.get_recent_attempts(
            db,
            user_id,
            security_config.LOCKOUT_DURATION_MINUTES
        )
        return len(attempts) < security_config.MAX_LOGIN_ATTEMPTS
    
    @staticmethod
    def record_login_attempt(db: Session, user_id: int, success: bool, ip_address: str):
        """Record a login attempt."""
        LoginAttempt.create(
            db,
            user_id=user_id,
            success=success,
            ip_address=ip_address
        )

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    request: Request = None
) -> User:
    """Get current authenticated user with enhanced security checks."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Verify token
        payload = TokenManager.verify_token(token, db)
        
        # Get user ID from token
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        
        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise credentials_exception
        
        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        # Log successful authentication
        if request:
            logger.info(f"User {user_id} authenticated from {request.client.host}")
        
        return user
        
    except JWTError:
        raise credentials_exception

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user 