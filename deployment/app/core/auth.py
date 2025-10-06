from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from jose import JWTError, jwt, ExpiredSignatureError
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging
import functools
from app.core.config import settings
from app.core.security_config import security_config
from app.db.database import get_db
from app.db.models import User, TokenBlacklist, LoginAttempt
from app.utils.security import generate_secure_random_string
from app.core.enhanced_auth import enhanced_auth_service

logger = logging.getLogger("auth")

# Valid test tokens for development and testing
VALID_TEST_TOKENS = ['test-token-for-cache-testing']

# Using bcrypt with optimized rounds for cloud environments
# Using 10 rounds for sub-second hashing in AWS App Runner
import os
bcrypt_rounds = 10 if os.getenv('AWS_LAMBDA_FUNCTION_NAME') or os.getenv('DOCKER_ENV') else 12
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=bcrypt_rounds
)

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def create_test_user() -> User:
    """Create a mock test user for development and testing purposes"""
    from datetime import datetime
    
    class TestUser:
        def __init__(self):
            self.id = 999999  # High ID to avoid conflicts
            self.email = "test@example.com"
            self.name = "Test User"
            self.timezone = "America/New_York"
            self.is_active = True
            self.profile_picture = None
            self.created_at = datetime.utcnow()
    
    return TestUser()

def jwt_required():
    """
    Decorator to enforce JWT authentication with enhanced security validation.
    This provides stronger authentication than the standard Depends(get_current_user).
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs (should be injected by Depends)
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required - no user found",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Additional security checks for sensitive operations (skip for test user)
            if hasattr(current_user, 'id') and current_user.id != 999999:
                if not current_user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Account is deactivated"
                    )
            
            # Log sensitive operation
            logger.info(f"JWT_REQUIRED: User {current_user.id} accessing {func.__name__}")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

class TokenManager:
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token with enhanced security."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "nbf": datetime.utcnow(),
            "jti": generate_secure_random_string(32),
            "type": "access"
        })
        
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        """Create a JWT refresh token with enhanced security."""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "nbf": datetime.utcnow(),
            "jti": generate_secure_random_string(32),
            "type": "refresh"
        })
        
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    @staticmethod
    async def verify_token(token: str, db: AsyncSession) -> Dict[str, Any]:
        """Verify a token with enhanced security checks."""
        # Check for test tokens first (development/testing)
        if settings.is_development() and token in VALID_TEST_TOKENS:
            logger.info(f"Test token detected: {token}")
            return {
                "user_id": 999999,
                "sub": "test@example.com",
                "type": "access",
                "test_token": True
            }
        
        try:
            # Check if token is blacklisted
            if await TokenBlacklist.is_blacklisted(db, token):
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
    async def check_login_attempts(db: AsyncSession, user_id: int) -> bool:
        """Check if user has exceeded maximum login attempts."""
        attempts = await LoginAttempt.get_recent_attempts(
            db,
            user_id,
            security_config.LOCKOUT_DURATION_MINUTES
        )
        return len(attempts) < security_config.MAX_LOGIN_ATTEMPTS
    
    @staticmethod
    async def record_login_attempt(db: AsyncSession, user_id: int, success: bool, ip_address: str):
        """Record a login attempt."""
        await LoginAttempt.create(
            db,
            user_id=user_id,
            success=success,
            ip_address=ip_address
        )

async def get_current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get the current user from request with enhanced authentication and automatic refresh."""
    
    # Always use enhanced auth service for consistent authentication
    user = await enhanced_auth_service.get_current_user_from_request(request, response, db)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Store user in request state for middleware compatibility
    request.state.user = user
    
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user (additional check for account status)."""
    # Skip active check for test user
    if hasattr(current_user, 'id') and current_user.id == 999999:
        return current_user
        
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )
    return current_user

# Helper function for non-request context authentication
async def get_current_user_from_token(token: str, db: AsyncSession) -> User:
    """Get current user from token without FastAPI request context."""
    try:
        # Verify token (includes test token support)
        payload = await TokenManager.verify_token(token, db)
        
        # Handle test tokens (development only)
        if payload.get("test_token") and settings.is_development():
            logger.info("Returning test user for development token (non-request context)")
            return create_test_user()
        
        user_id: int = payload.get("user_id")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        return user
        
    except Exception as e:
        # If it's already an HTTPException, re-raise it
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Token authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        ) 