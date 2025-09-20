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
    # Advanced JWT config (optional RS256 support with JWKS)
    JWT_SIGNING_ALG: str = Field("HS256", env="JWT_SIGNING_ALG")  # HS256 or RS256
    JWT_KID: Optional[str] = Field(None, env="JWT_KID")
    JWT_PRIVATE_KEY: Optional[str] = Field(None, env="JWT_PRIVATE_KEY")  # PEM for RS256
    JWT_PUBLIC_KEY: Optional[str] = Field(None, env="JWT_PUBLIC_KEY")    # PEM for RS256
    JWKS_CACHE_TTL: int = Field(86400, env="JWKS_CACHE_TTL")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # Short-lived access tokens
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    REMEMBER_ME_EXPIRE_DAYS: int = Field(30, env="REMEMBER_ME_EXPIRE_DAYS")  # Remember me duration
    PASSWORD_HASHER: str = Field("bcrypt", env="PASSWORD_HASHER")
    BCRYPT_ROUNDS: int = Field(14, env="BCRYPT_ROUNDS")

    # Cookie Settings
    COOKIE_SECURE: bool = Field(False, env="COOKIE_SECURE")  # Set to True in production with HTTPS
    COOKIE_HTTPONLY: bool = Field(True, env="COOKIE_HTTPONLY")
    COOKIE_SAMESITE: str = Field("none", env="COOKIE_SAMESITE")  # lax, strict, none
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

    # CSRF (double-submit cookie for cookie-auth flows)
    CSRF_ENABLED: bool = Field(True, env="CSRF_ENABLED")
    CSRF_HEADER_NAME: str = Field("X-CSRF-Token", env="CSRF_HEADER_NAME")

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
    
    # Redis Configuration
    REDIS_URL: str = Field("redis://localhost:6379/1", env="REDIS_URL")
    REDIS_CACHE_DEBUG: bool = Field(False, env="REDIS_CACHE_DEBUG")
    
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

    # Rate Limiting (per-IP)
    RATE_LIMIT_ENABLED: bool = Field(True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_MAX_REQUESTS: int = Field(500, env="RATE_LIMIT_MAX_REQUESTS")  # per window
    RATE_LIMIT_WINDOW_SECONDS: int = Field(60, env="RATE_LIMIT_WINDOW_SECONDS")  # 1 minute

    # Global token-bucket limiter (middleware)
    GLOBAL_RATE_LIMIT_CAPACITY: int = Field(120, env="GLOBAL_RATE_LIMIT_CAPACITY")
    GLOBAL_RATE_LIMIT_REFILL_RATE: float = Field(2.0, env="GLOBAL_RATE_LIMIT_REFILL_RATE")  # tokens per second

    # Feature quotas
    AI_CHAT_DAILY_LIMIT: int = Field(50, env="AI_CHAT_DAILY_LIMIT")
    FEEDBACK_DAILY_LIMIT: int = Field(1, env="FEEDBACK_DAILY_LIMIT")
    VOTING_IP_DAILY_LIMIT: int = Field(20, env="VOTING_IP_DAILY_LIMIT")

    # Email subscription limits
    EMAIL_SUBSCRIPTION_DAILY_LIMIT: int = Field(4, env="EMAIL_SUBSCRIPTION_DAILY_LIMIT")

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
    SECURITY_LOG_PATH: str = Field(
        default_factory=lambda: "/tmp/security.log" if (os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("AWS_EXECUTION_ENV")) else "security.log",
        env="SECURITY_LOG_PATH"
    )
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

    # Error tracking and tracing
    SENTRY_DSN: Optional[str] = Field(None, env="SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(0.2, env="SENTRY_TRACES_SAMPLE_RATE")
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(None, env="OTEL_EXPORTER_OTLP_ENDPOINT")
    OTEL_SERVICE_NAME: str = Field("refocused-backend", env="OTEL_SERVICE_NAME")

    # Deployment/migrations
    RUN_DB_MIGRATIONS_ON_STARTUP: bool = Field(True, env="RUN_DB_MIGRATIONS_ON_STARTUP")
    ALEMBIC_INI_PATH: str = Field("alembic.ini", env="ALEMBIC_INI_PATH")
    MIGRATIONS_PATH: str = Field("app/db/migrations", env="MIGRATIONS_PATH")

    # External Email Subscription API (API Gateway → Lambda)
    EMAIL_API_BASE_URL: str = Field(
        default="https://39qeq0f8u5.execute-api.us-east-1.amazonaws.com",
        env="EMAIL_API_BASE_URL",
    )
    EMAIL_API_KEY: Optional[str] = Field(None, env="EMAIL_API_KEY")
    EMAIL_API_PREFIX: str = Field("", env="EMAIL_API_PREFIX")  # No stage for HTTP API
    
    # External AI Service API (API Gateway → Lambda)
    AI_API_BASE_URL: str = Field(
        default="https://kzrybkpw5a.execute-api.us-east-1.amazonaws.com/api/ai",
        env="AI_API_BASE_URL",
    )
    AI_API_KEY: Optional[str] = Field(None, env="AI_API_KEY")
    
    # External Feature Voting API (API Gateway → Lambda)
    VOTING_API_BASE_URL: str = Field(
        default="https://example.execute-api.us-east-1.amazonaws.com/api/feature-voting",
        env="VOTING_API_BASE_URL",
    )
    FEATURE_VOTING_ENDPOINT: Optional[str] = Field(None, env="FEATURE_VOTING_ENDPOINT")  # Alternative config name
    VOTING_API_KEY: Optional[str] = Field(None, env="VOTING_API_KEY")
    VOTING_API_PREFIX: str = Field("", env="VOTING_API_PREFIX")  # Optional stage prefix

    # External Feedback API (API Gateway → Lambda)
    FEEDBACK_API_BASE_URL: Optional[str] = Field(None, env="FEEDBACK_API_BASE_URL")
    FEEDBACK_API_ENDPOINT: Optional[str] = Field(None, env="FEEDBACK_API_ENDPOINT")  # Alternative config name
    FEEDBACK_API_KEY: Optional[str] = Field(None, env="FEEDBACK_API_KEY")

    # External Avatar Generation API
    DICEBEAR_API_BASE_URL: str = Field(
        default="https://api.dicebear.com",
        env="DICEBEAR_API_BASE_URL",
    )

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
