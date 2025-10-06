from pydantic_settings import BaseSettings
from pydantic import Field

class SecurityConfig(BaseSettings):
    # Password validation settings (not in main config)
    PASSWORD_MIN_LENGTH: int = Field(8, env="PASSWORD_MIN_LENGTH")
    PASSWORD_MAX_LENGTH: int = Field(128, env="PASSWORD_MAX_LENGTH")
    PASSWORD_REQUIRE_UPPER: bool = Field(True, env="PASSWORD_REQUIRE_UPPER")
    PASSWORD_REQUIRE_LOWER: bool = Field(True, env="PASSWORD_REQUIRE_LOWER")
    PASSWORD_REQUIRE_NUMBER: bool = Field(True, env="PASSWORD_REQUIRE_NUMBER")
    PASSWORD_REQUIRE_SPECIAL: bool = Field(True, env="PASSWORD_REQUIRE_SPECIAL")
    
    # Login attempt limits (not in main config)
    MAX_LOGIN_ATTEMPTS: int = Field(5, env="MAX_LOGIN_ATTEMPTS")
    MAX_FAILED_LOGIN_ATTEMPTS: int = Field(5, env="MAX_FAILED_LOGIN_ATTEMPTS")
    LOCKOUT_DURATION_MINUTES: int = Field(15, env="LOCKOUT_DURATION_MINUTES")
    LOCKOUT_PERIOD_MINUTES: int = Field(15, env="LOCKOUT_PERIOD_MINUTES")
    
    # User agent and IP tracking (not in main config)
    MAX_USER_AGENTS_PER_IP: int = Field(5, env="MAX_USER_AGENTS_PER_IP")
    MAX_USER_AGENTS_PER_USER: int = Field(5, env="MAX_USER_AGENTS_PER_USER")
    MAX_IPS_PER_USER: int = Field(3, env="MAX_IPS_PER_USER")
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'

# Instantiate the config
security_config = SecurityConfig() 