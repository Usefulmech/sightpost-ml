from functools import lru_cache
from typing import List, Tuple

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIGHTPOST_", env_file=".env", extra="ignore")

    model_name: str = "buffalo_l"
    det_size: Tuple[int, int] = (640, 640)
    max_upload_mb: int = Field(default=8, ge=1, le=50)
    allowed_origins: List[str] = ["*"]
    skip_model_load: bool = False

    @field_validator("det_size", mode="before")
    @classmethod
    def parse_det_size(cls, value: object) -> Tuple[int, int]:
        if isinstance(value, str):
            width, height = value.split(",", maxsplit=1)
            return int(width.strip()), int(height.strip())
        return value  # type: ignore[return-value]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value  # type: ignore[return-value]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
