from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class SecuritySettings(BaseSettings):
    # Password rules - might need to adjust these
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 64
    
    # Basic security stuff
    CSRF_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 100  # TODO: Adjust based on usage
    RATE_LIMIT_PERIOD_SECONDS: int = 60
    
    # Security headers - might need to tweak these
    SECURITY_HSTS_ENABLED: bool = True
    SECURITY_HSTS_MAX_AGE: int = 31536000  # 1 year
    SECURITY_HSTS_INCLUDE_SUBDOMAINS: bool = True
    SECURITY_HSTS_PRELOAD: bool = True
    SECURITY_FRAME_DENY: bool = True
    SECURITY_XSS_PROTECTION: bool = True
    SECURITY_CONTENT_TYPE_NOSNIFF: bool = True
    
    # Logging setup
    SECURITY_LOG_ENABLED: bool = True
    SECURITY_LOG_PATH: str = "security.log"  # TODO: Set up log rotation
    SECURITY_ALERT_EMAIL: str = ""  # TODO: Set up alert email

class Settings(BaseSettings):
    # App settings
    APP_NAME: str = "ReFocused API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Auth stuff
    SECRET_KEY: str = "temporary-dev-key-replace-in-production"  # TODO: Change in prod
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # TODO: Maybe make this shorter
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # DB connection
    DATABASE_URL: str = "sqlite:///./app.db"  # TODO: Switch to Postgres in prod
    
    # Service URLs
    REDIS_URL: str = "redis://localhost:6379/0"  # TODO: Set up Redis in prod
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"
    API_V1_STR: str = "/api/v1"
    
    # CORS settings
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    
    # Security settings
    SECURITY: SecuritySettings = SecuritySettings()
    
    # SSL/TLS Settings (for production)
    SSL_ENABLED: bool = False
    SSL_CERT_FILE: str = ""
    SSL_KEY_FILE: str = ""
    
    # Enhanced configuration to protect sensitive values
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="forbid",
        case_sensitive=True,
        secrets=[
            "SECRET_KEY", 
            "DATABASE_URL", 
            "REDIS_URL",
            "SSL_KEY_FILE"
        ]
    )
    
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"
    
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

# Initialize settings
settings = Settings() 