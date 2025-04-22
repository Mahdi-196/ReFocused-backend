from typing import List, Dict, Any
from pydantic_settings import BaseSettings
import secrets
import string

class SecurityConfig(BaseSettings):
    # Authentication
    SECRET_KEY: str = secrets.token_urlsafe(64)
    ALGORITHM: str = "HS512"  # Using stronger algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Shorter token lifetime
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 30
    PASSWORD_HISTORY_SIZE: int = 5
    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_MAX_LENGTH: int = 128
    PASSWORD_REQUIRE_SPECIAL: bool = True
    PASSWORD_REQUIRE_NUMBER: bool = True
    PASSWORD_REQUIRE_UPPER: bool = True
    PASSWORD_REQUIRE_LOWER: bool = True
    
    # Session Security
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Strict"
    SESSION_LIFETIME_MINUTES: int = 30
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_PERIOD_SECONDS: int = 60
    RATE_LIMIT_BLOCK_DURATION: int = 300  # 5 minutes
    
    # Security Headers
    SECURITY_HSTS_ENABLED: bool = True
    SECURITY_HSTS_MAX_AGE: int = 31536000  # 1 year
    SECURITY_HSTS_INCLUDE_SUBDOMAINS: bool = True
    SECURITY_HSTS_PRELOAD: bool = True
    SECURITY_FRAME_DENY: bool = True
    SECURITY_XSS_PROTECTION: bool = True
    SECURITY_CONTENT_TYPE_NOSNIFF: bool = True
    SECURITY_REFERRER_POLICY: str = "strict-origin-when-cross-origin"
    SECURITY_PERMISSIONS_POLICY: str = "geolocation=(), camera=(), microphone=()"
    
    # CORS
    CORS_ALLOW_ORIGINS: List[str] = []
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = ["Authorization", "Content-Type", "Accept"]
    CORS_MAX_AGE: int = 600
    
    # Content Security Policy
    CSP_ENABLED: bool = True
    CSP_DIRECTIVES: Dict[str, List[str]] = {
        "default-src": ["'self'"],
        "script-src": ["'self'", "'unsafe-inline'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:", "https:"],
        "connect-src": ["'self'"],
        "font-src": ["'self'"],
        "object-src": ["'none'"],
        "media-src": ["'self'"],
        "frame-src": ["'none'"]
    }
    
    # Security Logging
    SECURITY_LOG_ENABLED: bool = True
    SECURITY_LOG_PATH: str = "security.log"
    SECURITY_LOG_LEVEL: str = "INFO"
    SECURITY_LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Database Security
    DB_ENCRYPTION_KEY: str = secrets.token_urlsafe(32)
    DB_CONNECTION_TIMEOUT: int = 30
    DB_MAX_CONNECTIONS: int = 20
    DB_SSL_MODE: str = "require"
    
    # File Upload Security
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_UPLOAD_TYPES: List[str] = ["image/jpeg", "image/png", "application/pdf"]
    UPLOAD_DIRECTORY: str = "uploads"
    
    # API Security
    API_VERSION_HEADER: str = "X-API-Version"
    API_KEY_HEADER: str = "X-API-Key"
    API_RATE_LIMIT_HEADER: str = "X-RateLimit-Limit"
    API_RATE_LIMIT_REMAINING: str = "X-RateLimit-Remaining"
    API_RATE_LIMIT_RESET: str = "X-RateLimit-Reset"
    
    # Security Monitoring
    MONITORING_ENABLED: bool = True
    MONITORING_INTERVAL_SECONDS: int = 300
    ALERT_THRESHOLD: int = 5
    ALERT_EMAIL: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        secrets_dir = "/run/secrets"  # For Docker secrets

security_config = SecurityConfig() 