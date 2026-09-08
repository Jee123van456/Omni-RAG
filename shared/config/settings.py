import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database Settings
    DATABASE_URL: str = Field(
        default="postgresql://omnirag_user:omnirag_password@localhost:5432/omnirag"
    )
    TEST_DATABASE_URL: str = Field(
        default="postgresql://omnirag_user:omnirag_password@localhost:5432/omnirag_test"
    )

    # Redis Settings
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # API Settings
    PORT: int = Field(default=8000)
    HOST: str = Field(default="0.0.0.0")
    ENV: str = Field(default="development")

    # LLM Settings (for later phases)
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None)
    COHERE_API_KEY: Optional[str] = Field(default=None)

    # Config model setup
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate a global settings object
settings = Settings()
