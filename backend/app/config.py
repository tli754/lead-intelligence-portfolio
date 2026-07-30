"""Application configuration.

All environment-driven configuration is centralised here using
pydantic-settings. No module outside this file should read `os.environ`
directly — see ARCHITECTURE.md.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings.

    Values are read from process environment variables, falling back to a
    local `.env` file (see `.env.example` for the full list of variables
    this feature depends on).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "lead_intelligence"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"
    REDIS_URL: str = "redis://localhost:6379/0"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        """CORS_ALLOWED_ORIGINS as a list, split on commas."""
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
