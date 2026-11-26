from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    keitaro_base_url: str = "https://keitaro-for-tests.etolegko.com"
    keitaro_api_key: str = ""
    keitaro_domain_id: int | None = None
    keitaro_group_id: int | None = None
    keitaro_traffic_source_id: int | None = None
    campaign_prefix: str = Field(default="test_ivanov_", min_length=1)
    seed_campaign_name: str = "seed_campaign"
    seed_geo: str = Field(default="AU", min_length=2, max_length=2)
    seed_offer_id: int = Field(default=18001, gt=0)
    database_url: str = "sqlite:///./keitaro_wrapper.db"

    @field_validator("keitaro_base_url")
    @classmethod
    def strip_admin_suffix(cls, value: str) -> str:
        return value.rstrip("/").removesuffix("/admin")

    @field_validator("seed_geo")
    @classmethod
    def normalize_seed_geo(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()

