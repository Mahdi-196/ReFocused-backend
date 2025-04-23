from typing import List, Dict, Any, Optional
from pydantic_settings import BaseSettings
import secrets
import string
from pydantic import Field

class SecurityConfig(BaseSettings):
    # Core security settings
    SECRET_KEY: str = "your-very-secret-key-for-dev"  # Change in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Password hashing
    PASSWORD_HASHER: str = "bcrypt"
    BCRYPT_ROUNDS: int = 12
    
    # CORS settings
    CORS_ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOWED_METHODS: List[str] = ["*"]
    CORS_ALLOWED_HEADERS: List[str] = ["*"]
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 100  # Max requests
    RATE_LIMIT_PERIOD_SECONDS: int = 60  # Per 60 seconds
    RATE_LIMIT_BLOCK_DURATION: int = 300 # Block for 300 seconds (5 minutes) if limit exceeded
    
    # Security Headers
    SECURITY_HSTS_ENABLED: bool = True # Use True in production with HTTPS
    SECURITY_HSTS_MAX_AGE: int = 31536000 # 1 year
    SECURITY_HSTS_INCLUDE_SUBDOMAINS: bool = True
    SECURITY_HSTS_PRELOAD: bool = False # Consider setting to True after verification
    SECURITY_FRAME_DENY: bool = True # X-Frame-Options: DENY
    SECURITY_XSS_PROTECTION: bool = True # X-XSS-Protection: 1; mode=block
    SECURITY_CONTENT_TYPE_NOSNIFF: bool = True # X-Content-Type-Options: nosniff
    SECURITY_REFERRER_POLICY: str = "strict-origin-when-cross-origin" # Added
    SECURITY_PERMISSIONS_POLICY: str = "camera=(), microphone=(), geolocation=()" # Example restrictive policy
    
    # Content Security Policy (CSP) - Define sources allowed for content
    CSP_ENABLED: bool = True
    CSP_DIRECTIVES: Dict[str, List[str]] = {
        "default-src": ["'self'"],
        "script-src": ["'self'", "'unsafe-inline'"], # Allow inline scripts if needed, but be cautious
        "style-src": ["'self'", "'unsafe-inline'"], # Allow inline styles if needed
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'"], # Allow connections to own origin
        "frame-ancestors": ["'none'"] # Equivalent to X-Frame-Options: DENY
    }
    
    # Max Upload Size for RequestValidationMiddleware
    MAX_UPLOAD_SIZE: int = 10485760 # 10MB in bytes
    
    # Logging
    SECURITY_LOG_ENABLED: bool = True
    SECURITY_LOG_PATH: str = "security_events.log"
    SECURITY_LOG_LEVEL: str = "INFO"
    SECURITY_LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Miscellaneous
    TRUSTED_HOSTS: Optional[List[str]] = None # e.g., ["example.com", "*.example.com"] - None allows any host (dev only)
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore' # Ignore extra fields from .env instead of allow

# Instantiate the config
security_config = SecurityConfig() 