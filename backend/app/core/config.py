from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    APP_NAME: str = "FlowSentry"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Security
    ENCRYPTION_KEY: str = ""
    LOCAL_DEV_JWT_SECRET: str = ""
    ALLOW_PRIVATE_INTEGRATION_HOSTS: bool = False

    # Auth
    AUTH_MODE: Literal["supabase", "local_dev"] = "supabase"
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Database & Redis
    DATABASE_URL: str = "postgresql+psycopg://flowsentry:flowsentry@localhost:5432/flowsentry"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # AI (Provider-independent)
    AI_PROVIDER: Literal["openai", "gemini", "none"] = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Notifications
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "alerts@flowsentry.local"
    SMTP_USE_TLS: bool = True

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_production_guards(self) -> Settings:
        if self.ENVIRONMENT == "production":
            if self.AUTH_MODE != "supabase":
                raise ValueError("AUTH_MODE must be 'supabase' when ENVIRONMENT=production")
            if self.DEBUG:
                raise ValueError("DEBUG must be false when ENVIRONMENT=production")
            if not self.ENCRYPTION_KEY:
                raise ValueError("ENCRYPTION_KEY must be set in production")
            if "*" in self.allowed_origins_list:
                raise ValueError("Wildcard CORS origins are forbidden in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
