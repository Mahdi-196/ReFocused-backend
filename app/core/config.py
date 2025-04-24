from typing import List, Dict
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

    # Auth
    SECRET_KEY: str = Field("dev-secret-key-change-in-production", env="SECRET_KEY")
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    PASSWORD_HASHER: str = Field("bcrypt", env="PASSWORD_HASHER")
    BCRYPT_ROUNDS: int = Field(12, env="BCRYPT_ROUNDS")
    
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
    CORS_ALLOWED_ORIGINS: List[str] = Field(default_factory=list, env="CORS_ALLOWED_ORIGINS")
    CORS_ALLOW_CREDENTIALS: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")
    CORS_ALLOWED_METHODS: List[str] = Field(default_factory=lambda: ["*"], env="CORS_ALLOWED_METHODS")
    CORS_ALLOWED_HEADERS: List[str] = Field(default_factory=lambda: ["*"], env="CORS_ALLOWED_HEADERS")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_MAX_REQUESTS: int = Field(100, env="RATE_LIMIT_MAX_REQUESTS")
    RATE_LIMIT_PERIOD_SECONDS: int = Field(60, env="RATE_LIMIT_PERIOD_SECONDS")
    RATE_LIMIT_BLOCK_DURATION: int = Field(300, env="RATE_LIMIT_BLOCK_DURATION")

    # Rate‑limit headers
    API_RATE_LIMIT_REMAINING: str = Field("X-RateLimit-Remaining", env="API_RATE_LIMIT_REMAINING")
    API_RATE_LIMIT_RESET:     str = Field("X-RateLimit-Reset",     env="API_RATE_LIMIT_RESET")
    API_RATE_LIMIT_HEADER:    str = Field("X-RateLimit-Limit",     env="API_RATE_LIMIT_HEADER")
    API_VERSION_HEADER:       str = Field("X-API-Version",         env="API_VERSION_HEADER")

    # Security Headers
    SECURITY_HSTS_ENABLED: bool = Field(True, env="SECURITY_HSTS_ENABLED")
    SECURITY_HSTS_MAX_AGE: int = Field(31_536_000, env="SECURITY_HSTS_MAX_AGE")
    SECURITY_HSTS_INCLUDE_SUBDOMAINS: bool = Field(True, env="SECURITY_HSTS_INCLUDE_SUBDOMAINS")
    SECURITY_HSTS_PRELOAD: bool = Field(False, env="SECURITY_HSTS_PRELOAD")
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

    # SSL/TLS
    SSL_ENABLED: bool = Field(False, env="SSL_ENABLED")

    # Helpers
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
