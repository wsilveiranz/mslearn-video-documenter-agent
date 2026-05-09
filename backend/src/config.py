"""Application configuration using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Processing Mode ---
    processing_mode: Literal["cloud", "local"] = Field(
        default="cloud",
        description="Use 'cloud' for Azure services or 'local' for local-only processing",
    )

    # --- Azure AI Foundry ---
    foundry_project_endpoint: str = Field(
        default="",
        description="Azure AI Foundry project endpoint (e.g., https://your-project.services.ai.azure.com)",
    )
    foundry_model: str = Field(
        default="gpt-4o",
        description="Default model deployment name in Foundry",
    )
    foundry_model_mini: str = Field(
        default="gpt-4o-mini",
        description="Smaller model for simpler tasks (evaluation, classification)",
    )

    # --- Azure Blob Storage ---
    blob_connection_string: str = Field(default="", description="Azure Blob Storage connection string")
    blob_container_name: str = Field(default="video-documenter", description="Container name for video files")

    # --- Azure AI Speech (cloud mode) ---
    speech_service_key: str = Field(default="", description="Azure AI Speech service key")
    speech_service_region: str = Field(default="eastus", description="Azure AI Speech region")

    # --- Azure Video Indexer (cloud mode) ---
    video_indexer_account_id: str = Field(default="", description="Video Indexer account ID")
    video_indexer_resource_id: str = Field(
        default="",
        description="Full ARM resource ID for Video Indexer",
    )
    video_indexer_api_key: str = Field(default="", description="Video Indexer API key")
    video_indexer_location: str = Field(default="trial", description="Video Indexer account location")

    # --- Local Mode Settings ---
    whisper_model: str = Field(
        default="base",
        description="Whisper model size: tiny, base, small, medium, large",
    )
    ffmpeg_path: str = Field(default="ffmpeg", description="Path to FFmpeg binary")

    # --- Output ---
    output_directory: str = Field(default="./output", description="Directory for generated documents")

    # --- Server ---
    host: str = Field(default="127.0.0.1", description="FastAPI server host")
    port: int = Field(default=8000, description="FastAPI server port")
    log_level: str = Field(default="info", description="Logging level")

    # --- Feature Flags ---
    enable_youtube_download: bool = Field(
        default=False,
        description="Enable yt-dlp YouTube downloading (optional, review ToS)",
    )
    max_video_duration_minutes: int = Field(
        default=15,
        description="Maximum video duration in minutes",
    )
    max_video_size_mb: int = Field(
        default=2048,
        description="Maximum video file size in MB",
    )

    @property
    def is_cloud_mode(self) -> bool:
        return self.processing_mode == "cloud"

    @property
    def is_local_mode(self) -> bool:
        return self.processing_mode == "local"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
