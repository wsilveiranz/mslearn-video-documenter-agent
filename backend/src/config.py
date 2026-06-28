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
    processing_mode: Literal["auto", "cloud", "local"] = Field(
        default="auto",
        description=(
            "'auto' selects per-stage clients based on what is configured "
            "(Foundry/Video Indexer for extraction, Copilot proxy for downstream). "
            "'cloud' forces Azure Foundry everywhere. "
            "'local' forces local extraction + Copilot proxy downstream."
        ),
    )

    # --- Environment ---
    environment: Literal["development", "production"] = Field(
        default="development",
        description="Runtime environment — controls uvicorn reload and debug behavior",
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
    blob_account_url: str = Field(
        default="",
        description="Azure Blob Storage account URL (e.g., https://stvideodocumenter.blob.core.windows.net)",
    )
    blob_container_name: str = Field(default="video-documenter", description="Container name for video files")
    blob_retention_hours: int = Field(
        default=1,
        description="Maximum blob retention in hours — used as SAS token expiry",
    )

    # --- Azure AI Speech (cloud mode) ---
    speech_service_endpoint: str = Field(default="", description="Azure AI Speech endpoint URL")
    speech_service_region: str = Field(default="eastus", description="Azure AI Speech region")

    # --- Azure Video Indexer (cloud mode) ---
    video_indexer_account_id: str = Field(default="", description="Video Indexer account ID")
    video_indexer_resource_id: str = Field(
        default="",
        description="Full ARM resource ID for Video Indexer",
    )
    video_indexer_location: str = Field(default="trial", description="Video Indexer account location")
    vi_indexing_timeout_s: int = Field(
        default=1200,
        description="Maximum time in seconds to wait for Video Indexer to process a video (default: 20 min)",
    )
    vi_poll_interval_s: int = Field(
        default=15,
        description="Seconds between Video Indexer polling requests",
    )
    vi_progress_interval_s: int = Field(
        default=30,
        description="Minimum seconds between progress emissions to WebSocket (independent of poll frequency)",
    )

    # --- Local Mode Settings ---
    whisper_model: str = Field(
        default="base",
        description="Whisper model size: tiny, base, small, medium, large",
    )
    ffmpeg_path: str = Field(default="ffmpeg", description="Path to FFmpeg binary")

    # --- Local Mode: Copilot LM Proxy ---
    copilot_proxy_url: str = Field(
        default="",
        description="URL of the VS Code Copilot LM Proxy (e.g., http://localhost:3001). "
        "When set and processing_mode is 'local', LLM calls route through Copilot instead of Azure Foundry.",
    )
    copilot_proxy_model: str = Field(
        default="copilot-auto",
        description="Model name to request from the Copilot proxy (copilot-auto for best available)",
    )
    copilot_proxy_secret: str = Field(
        default="",
        description="Shared secret for authenticating requests to the Copilot LM Proxy",
    )

    # --- MCP Integration ---
    mcp_learn_endpoint: str = Field(
        default="https://learn.microsoft.com/api/mcp",
        description="Microsoft Learn MCP Server endpoint (Streamable HTTP)",
    )
    mcp_cache_ttl_seconds: int = Field(
        default=3600,
        description="TTL in seconds for MCP response cache (default: 1 hour)",
    )
    mcp_request_timeout_seconds: int = Field(
        default=30,
        description="Timeout in seconds for individual MCP tool calls",
    )
    mcp_workiq_enabled: bool = Field(
        default=False,
        description="Enable Work IQ MCP integration for M365 context enrichment",
    )
    mcp_workiq_npx_path: str = Field(
        default="npx",
        description="Path to npx binary for launching Work IQ MCP server",
    )
    mcp_graceful_degradation: bool = Field(
        default=True,
        description="If True, agents continue without grounding when MCP servers are unavailable",
    )

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
    def is_auto_mode(self) -> bool:
        return self.processing_mode == "auto"

    @property
    def is_cloud_mode(self) -> bool:
        return self.processing_mode == "cloud"

    @property
    def is_local_mode(self) -> bool:
        return self.processing_mode == "local"

    @property
    def use_copilot_proxy(self) -> bool:
        """Whether to use Copilot LM Proxy for LLM calls (local mode with proxy configured)."""
        return self.is_local_mode and bool(self.copilot_proxy_url)

    @property
    def foundry_available(self) -> bool:
        """Whether Azure AI Foundry is configured (endpoint set)."""
        return bool(self.foundry_project_endpoint)

    @property
    def video_indexer_available(self) -> bool:
        """Whether Azure Video Indexer is configured for cloud extraction."""
        return bool(self.video_indexer_account_id and self.video_indexer_resource_id)

    @property
    def copilot_proxy_available(self) -> bool:
        """Whether the Copilot LM Proxy is configured for downstream LLM calls."""
        return bool(self.copilot_proxy_url)

    def get_azure_credential(self):
        """Get Azure credential for service authentication.

        Uses DefaultAzureCredential which supports:
        - Managed Identity (production/Foundry hosted agents)
        - Azure CLI credential (local development)
        - Environment variables (CI/CD)
        - VS Code credential (local development)
        """
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential()


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
