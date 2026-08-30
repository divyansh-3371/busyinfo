"""Application settings, loaded from environment variables (.env in local dev)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173"

    # Stale-approval alert thresholds (days). See docs/decisions.md.
    stale_alert_days: int = 3
    stale_alert_snooze_days: int = 3

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
