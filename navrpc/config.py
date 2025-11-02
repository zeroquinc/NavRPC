import yaml
import os
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field

class NavidromeConfig(BaseModel):
    """Navidrome Connection Settings."""
    base_url: HttpUrl
    username: str
    password: str

class IntegrationConfig(BaseModel):
    """Integration API Keys."""
    imgur_client_id: str
    discord_client_id: str
    discord_asset_name: Optional[str] = None

class ImageConfig(BaseModel):
    """Image Optimization Settings."""
    max_size: int = 512
    jpeg_quality: int = 85
    max_file_bytes: int = 4194304 # 4MB

class Settings(BaseModel):
    """Master configuration model."""
    navidrome: NavidromeConfig
    integration: IntegrationConfig
    image: ImageConfig
    general: dict = Field(default_factory=dict) # Catch all for general settings like cache/poll

    @property
    def poll_interval(self) -> int:
        return self.general.get("poll_interval_seconds", 5)

    @property
    def cache_file(self) -> str:
        return self.general.get("cache_file", "cache.json")

    @property
    def strip_title_subtitle(self) -> bool:
        return self.general.get("strip_title_subtitle", True)


def load_config(path: str = "config.yaml") -> Settings:
    """Loads and validates configuration from a YAML file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found at: {path}. Use config.yaml.example to create one.")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Use **data for Pydantic's dict-to-model instantiation
    return Settings(**data)
