from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Project Info
    APP_NAME: str
    ENVIRONMENT: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    DATABASE_URL: str
    REDIS_URL: str
    FRONTEND_URL: str
    BACKEND_URL: str
    API_V1_STR: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="forbid",
        case_sensitive=True
    )

settings = Settings() 