from typing import List, Dict, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from datetime import datetime, date


class Settings(BaseSettings):
    # Application
    APP_NAME: str = Field("ReFocused API", env="APP_NAME")
    APP_ENV: str = Field("production", env="APP_ENV")
    DEBUG: bool = Field(False, env="DEBUG")
    API_V1_STR: str = Field("/api/v1", env="API_V1_STR")

    # Server
    HOST: str = Field("0.0.0.0", env="HOST")
    PORT: int = Field(8000, env="PORT")

    # Auth - Professional Grade Settings
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # Short-lived access tokens
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    REMEMBER_ME_EXPIRE_DAYS: int = Field(30, env="REMEMBER_ME_EXPIRE_DAYS")  # Remember me duration
    PASSWORD_HASHER: str = Field("bcrypt", env="PASSWORD_HASHER")
    BCRYPT_ROUNDS: int = Field(14, env="BCRYPT_ROUNDS")

    # Cookie Settings
    COOKIE_SECURE: bool = Field(False, env="COOKIE_SECURE")  # Set to True in production with HTTPS
    COOKIE_HTTPONLY: bool = Field(True, env="COOKIE_HTTPONLY")
    COOKIE_SAMESITE: str = Field("lax", env="COOKIE_SAMESITE")  # lax, strict, none
    COOKIE_DOMAIN: Optional[str] = Field(None, env="COOKIE_DOMAIN")
    COOKIE_PATH: str = Field("/", env="COOKIE_PATH")
    COOKIE_MAX_AGE: int = Field(86400 * 30, env="COOKIE_MAX_AGE")  # 30 days

    # Session Settings
    SESSION_EXPIRE_MINUTES: int = Field(480, env="SESSION_EXPIRE_MINUTES")  # 8 hours default
    SESSION_AUTO_REFRESH: bool = Field(True, env="SESSION_AUTO_REFRESH")
    SESSION_REMEMBER_ME_DAYS: int = Field(30, env="SESSION_REMEMBER_ME_DAYS")

    # Auto-refresh settings
    AUTO_REFRESH_THRESHOLD_MINUTES: int = Field(5, env="AUTO_REFRESH_THRESHOLD_MINUTES")  # Refresh if expires in 5 min
    AUTO_REFRESH_ENABLED: bool = Field(True, env="AUTO_REFRESH_ENABLED")

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(..., env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str = Field(..., env="GOOGLE_CLIENT_SECRET")
    
    # Auth Flow Configuration
    AUTH_TOKEN_URL: str = Field("/api/v1/auth/login", env="AUTH_TOKEN_URL")
    AUTH_ALLOW_JSON: bool = Field(True, env="AUTH_ALLOW_JSON")
    AUTH_ALLOW_FORM: bool = Field(True, env="AUTH_ALLOW_FORM")
    AUTH_DEFAULT_GRANT_TYPE: str = Field("password", env="AUTH_DEFAULT_GRANT_TYPE")
    AUTH_REQUIRE_GRANT_TYPE: bool = Field(False, env="AUTH_REQUIRE_GRANT_TYPE")

    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(20, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(10, env="DATABASE_MAX_OVERFLOW")
    DATABASE_POOL_TIMEOUT: int = Field(30, env="DATABASE_POOL_TIMEOUT")
    DATABASE_POOL_RECYCLE: int = Field(1800, env="DATABASE_POOL_RECYCLE")
    
    # Celery Configuration
    CELERY_BROKER_URL: str = Field("redis://localhost:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field("redis://localhost:6379/0", env="CELERY_RESULT_BACKEND")

    # CORS
    CORS_ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"], 
        env="CORS_ALLOWED_ORIGINS"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")
    CORS_ALLOWED_METHODS: List[str] = Field(default_factory=lambda: ["*"], env="CORS_ALLOWED_METHODS")
    CORS_ALLOWED_HEADERS: List[str] = Field(default_factory=lambda: ["*"], env="CORS_ALLOWED_HEADERS")

    # Rate Limiting - DISABLED for development
    RATE_LIMIT_ENABLED: bool = Field(True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_MAX_REQUESTS: int = Field(100, env="RATE_LIMIT_MAX_REQUESTS")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(3600, env="RATE_LIMIT_WINDOW_SECONDS")  # 1 hour

    # Rate‑limit headers
    API_RATE_LIMIT_REMAINING: str = Field("X-RateLimit-Remaining", env="API_RATE_LIMIT_REMAINING")
    API_RATE_LIMIT_RESET:     str = Field("X-RateLimit-Reset",     env="API_RATE_LIMIT_RESET")
    API_RATE_LIMIT_HEADER:    str = Field("X-RateLimit-Limit",     env="API_RATE_LIMIT_HEADER")
    API_VERSION_HEADER:       str = Field("X-API-Version",         env="API_VERSION_HEADER")

    # Security Headers (HSTS removed since HTTPS handled by AWS)
    SECURITY_FRAME_DENY: bool = Field(True, env="SECURITY_FRAME_DENY")
    SECURITY_XSS_PROTECTION: bool = Field(True, env="SECURITY_XSS_PROTECTION")
    SECURITY_CONTENT_TYPE_NOSNIFF: bool = Field(True, env="SECURITY_CONTENT_TYPE_NOSNIFF")
    SECURITY_REFERRER_POLICY: str = Field("strict-origin-when-cross-origin", env="SECURITY_REFERRER_POLICY")
    SECURITY_PERMISSIONS_POLICY: str = Field("camera=(), microphone=(), geolocation=()", env="SECURITY_PERMISSIONS_POLICY")

    # Content Security Policy
    CSP_ENABLED: bool = Field(True, env="CSP_ENABLED")
    CSP_DIRECTIVES: Dict[str, str] = Field(
        default_factory=lambda: {
            "default-src": "'self'",
            "script-src": "'self' 'unsafe-inline'",
            "style-src": "'self' 'unsafe-inline'",
            "img-src": "'self' data:",
        },
        env="CSP_DIRECTIVES",
    )

    # Security Logging
    SECURITY_LOG_ENABLED: bool = Field(True, env="SECURITY_LOG_ENABLED")
    SECURITY_LOG_PATH: str = Field("security.log", env="SECURITY_LOG_PATH")
    SECURITY_LOG_LEVEL: str = Field("INFO", env="SECURITY_LOG_LEVEL")
    SECURITY_LOG_FORMAT: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
        env="SECURITY_LOG_FORMAT"
    )

    # Max Upload Size
    MAX_UPLOAD_SIZE: int = Field(10 * 1024 * 1024, env="MAX_UPLOAD_SIZE")

    # Trusted Hosts
    TRUSTED_HOSTS: List[str] = Field(default=["*"], env="TRUSTED_HOSTS")

    # Security thresholds
    SUSPICIOUS_REQUEST_THRESHOLD: int = Field(50, env="SUSPICIOUS_REQUEST_THRESHOLD")
    FAILED_AUTH_THRESHOLD: int = Field(5, env="FAILED_AUTH_THRESHOLD")

    # Helpers
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"
    
    def get_current_date(self) -> date:
        """Get the current date (always real date now)"""
        return datetime.now().date()

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()
