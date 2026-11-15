from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    REPOS_ROOT: Path = Field(
        default=Path("."),
        description="Root directory containing local repositories.",
    )
    GIT_REMOTE_BASE: str = Field(
        default="https://github.com",
        description="Base URL used when cloning repositories.",
    )
    ALLOW_LOCAL_REMOTES: bool = Field(
        default=False,
        description="Allow local clone remotes for controlled tests.",
    )
    GITHUB_TOKEN: SecretStr | None = Field(
        default=None,
        description="GitHub access token used for read-only requests.",
    )
    ANTHROPIC_API_KEY: SecretStr | None = Field(
        default=None,
        description="Anthropic API key used for symbol explanations.",
    )
    EXPLAIN_PROVIDER: Literal["anthropic", "ollama"] = Field(
        default="anthropic",
        description="Provider used for symbol explanations.",
    )
    EXPLAIN_MODEL: str = Field(
        default="claude-sonnet-5-5",
        description="Anthropic model used for symbol explanations.",
    )
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Base URL for the local Ollama server.",
    )
    OLLAMA_MODEL: str = Field(
        default="llama3.2:3b",
        description="Ollama model used for symbol explanations.",
    )
    LOG_LEVEL: str = Field(default="INFO", description="Logging level.")

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must start with http:// or https://")
        return value
