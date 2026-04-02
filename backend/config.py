from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""

    DOWNLOAD_DIR: str = "./downloads"
    TEMP_DIR: str = "./temp"
    MAX_CONCURRENT_DOWNLOADS: int = 3
    FILE_CLEANUP_INTERVAL_MINUTES: int = 60
    MAX_PLAYLIST_SIZE: int = 500

    HOST: str = "0.0.0.0"
    PORT: int = 8000


settings = Settings()
