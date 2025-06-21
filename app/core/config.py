from typing import List, Dict, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = Field("ReFocused API", env="APP_NAME")
    APP_ENV: str = Field("development", env="APP_ENV")
    DEBUG: bool = Field(True, env="DEBUG")
    API_V1_STR: str = Field("/api/v1", env="API_V1_STR")

    # Server
    HOST: str = Field("0.0.0.0", env="HOST")
    PORT: int = Field(8000, env="PORT")

    # Auth - Secure defaults
    SECRET_KEY: str = Field(..., env="SECRET_KEY", min_length=32)  # Force secret key to be set
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(15, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # Shorter for security
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(1, env="REFRESH_TOKEN_EXPIRE_DAYS")  # Shorter for security
    PASSWORD_HASHER: str = Field("bcrypt", env="PASSWORD_HASHER")
    BCRYPT_ROUNDS: int = Field(14, env="BCRYPT_ROUNDS")  # Higher rounds for security
    
    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = Field(None, env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(None, env="GOOGLE_CLIENT_SECRET")
    
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

    # CORS
    CORS_ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"], 
        env="CORS_ALLOWED_ORIGINS"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")
    CORS_ALLOWED_METHODS: List[str] = Field(default_factory=lambda: ["*"], env="CORS_ALLOWED_METHODS")
    CORS_ALLOWED_HEADERS: List[str] = Field(default_factory=lambda: ["*"], env="CORS_ALLOWED_HEADERS")

    # Rate Limiting - High limits for development
    RATE_LIMIT_ENABLED: bool = Field(True, env="RATE_LIMIT_ENABLED")  # Re-enabled with high limits
    RATE_LIMIT_MAX_REQUESTS: int = Field(15000, env="RATE_LIMIT_MAX_REQUESTS")  # Increased to 15000
    RATE_LIMIT_PERIOD_SECONDS: int = Field(60, env="RATE_LIMIT_PERIOD_SECONDS")
    RATE_LIMIT_BLOCK_DURATION: int = Field(300, env="RATE_LIMIT_BLOCK_DURATION")

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
    SECURITY_LOG_PATH: str = Field("security_events.log", env="SECURITY_LOG_PATH")
    SECURITY_LOG_LEVEL: str = Field("INFO", env="SECURITY_LOG_LEVEL")
    SECURITY_LOG_FORMAT: str = Field("%(asctime)s - %(levelname)s - %(message)s", env="SECURITY_LOG_FORMAT")

    # Max Upload Size
    MAX_UPLOAD_SIZE: int = Field(10 * 1024 * 1024, env="MAX_UPLOAD_SIZE")

    # Trusted Hosts
    TRUSTED_HOSTS: List[str] = Field(default_factory=list, env="TRUSTED_HOSTS")

    # Mock date support for testing
    MOCK_DATE_ENABLED: bool = Field(False, env="MOCK_DATE_ENABLED")
    MOCK_DATE: str = Field("2025-06-23", env="MOCK_DATE")  # Format: YYYY-MM-DD

    # Helpers
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"
    
    def get_current_date(self):
        """Get current date - can be mocked for testing"""
        if self.MOCK_DATE_ENABLED and self.is_development():
            from datetime import datetime
            return datetime.strptime(self.MOCK_DATE, "%Y-%m-%d").date()
        from datetime import date
        return date.today()

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()
