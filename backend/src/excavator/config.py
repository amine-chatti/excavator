from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DATABASE_URL: str = Field(
        default="postgresql+psycopg://excavator:excavator@localhost:5432/excavator",
        description="Primary database connection string.",
    )
    GITHUB_TOKEN: SecretStr | None = Field(
        default=None,
        description="GitHub access token used for read-only requests.",
    )
    LOG_LEVEL: str = Field(default="INFO", description="Logging level.")
