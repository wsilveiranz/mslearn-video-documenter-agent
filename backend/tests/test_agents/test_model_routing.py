"""Unit tests for per-stage model routing.

Covers:
- Settings availability properties (foundry_available, video_indexer_available,
  copilot_proxy_available, is_auto_mode).
- resolve_extraction_mode routing logic.
- create_extraction_client factory routing.
- create_llm_client downstream routing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.agents.orchestrator import (
    create_extraction_client,
    create_llm_client,
    resolve_extraction_mode,
)
from src.config import Settings
from src.models.video import ProcessingMode

# ═══════════════════════════════════════════════════════════
# A. Settings availability properties
# ═══════════════════════════════════════════════════════════


class TestSettingsAvailabilityProperties:
    """Settings availability properties derived from field values."""

    # foundry_available

    def test_foundry_available_when_endpoint_set(self):
        s = Settings(foundry_project_endpoint="https://x.services.ai.azure.com")
        assert s.foundry_available is True

    def test_foundry_not_available_when_empty(self):
        s = Settings(foundry_project_endpoint="")
        assert s.foundry_available is False

    # video_indexer_available

    def test_video_indexer_available_when_both_fields_set(self):
        s = Settings(video_indexer_account_id="account-id", video_indexer_resource_id="resource-id")
        assert s.video_indexer_available is True

    def test_video_indexer_not_available_when_only_account_set(self):
        s = Settings(video_indexer_account_id="account-id", video_indexer_resource_id="")
        assert s.video_indexer_available is False

    def test_video_indexer_not_available_when_only_resource_set(self):
        s = Settings(video_indexer_account_id="", video_indexer_resource_id="resource-id")
        assert s.video_indexer_available is False

    def test_video_indexer_not_available_when_both_empty(self):
        s = Settings(video_indexer_account_id="", video_indexer_resource_id="")
        assert s.video_indexer_available is False

    # copilot_proxy_available

    def test_copilot_proxy_available_when_url_set(self):
        s = Settings(copilot_proxy_url="http://localhost:3001")
        assert s.copilot_proxy_available is True

    def test_copilot_proxy_not_available_when_empty(self):
        s = Settings(copilot_proxy_url="")
        assert s.copilot_proxy_available is False

    # is_auto_mode

    def test_is_auto_mode_when_auto(self):
        s = Settings(processing_mode="auto")
        assert s.is_auto_mode is True

    def test_is_not_auto_mode_when_cloud(self):
        s = Settings(processing_mode="cloud")
        assert s.is_auto_mode is False

    def test_is_not_auto_mode_when_local(self):
        s = Settings(processing_mode="local")
        assert s.is_auto_mode is False


# ═══════════════════════════════════════════════════════════
# A. resolve_extraction_mode
# ═══════════════════════════════════════════════════════════


class TestResolveExtractionMode:
    """resolve_extraction_mode: explicit passthrough and settings-based routing."""

    def test_explicit_cloud_passthrough(self):
        assert resolve_extraction_mode(ProcessingMode.CLOUD) == ProcessingMode.CLOUD

    def test_explicit_local_passthrough(self):
        assert resolve_extraction_mode(ProcessingMode.LOCAL) == ProcessingMode.LOCAL

    @patch("src.agents.orchestrator.get_settings")
    def test_settings_cloud_returns_cloud(self, mock_get_settings):
        s = MagicMock()
        s.processing_mode = "cloud"
        mock_get_settings.return_value = s
        assert resolve_extraction_mode() == ProcessingMode.CLOUD

    @patch("src.agents.orchestrator.get_settings")
    def test_settings_local_returns_local(self, mock_get_settings):
        s = MagicMock()
        s.processing_mode = "local"
        mock_get_settings.return_value = s
        assert resolve_extraction_mode() == ProcessingMode.LOCAL

    @patch("src.agents.orchestrator.get_settings")
    def test_auto_with_foundry_and_vi_returns_cloud(self, mock_get_settings):
        s = MagicMock()
        s.processing_mode = "auto"
        s.foundry_available = True
        s.video_indexer_available = True
        mock_get_settings.return_value = s
        assert resolve_extraction_mode() == ProcessingMode.CLOUD

    @patch("src.agents.orchestrator.get_settings")
    def test_auto_without_foundry_returns_local(self, mock_get_settings):
        s = MagicMock()
        s.processing_mode = "auto"
        s.foundry_available = False
        s.video_indexer_available = True
        mock_get_settings.return_value = s
        assert resolve_extraction_mode() == ProcessingMode.LOCAL

    @patch("src.agents.orchestrator.get_settings")
    def test_auto_without_video_indexer_returns_local(self, mock_get_settings):
        s = MagicMock()
        s.processing_mode = "auto"
        s.foundry_available = True
        s.video_indexer_available = False
        mock_get_settings.return_value = s
        assert resolve_extraction_mode() == ProcessingMode.LOCAL

    @patch("src.agents.orchestrator.get_settings")
    def test_auto_without_either_returns_local(self, mock_get_settings):
        s = MagicMock()
        s.processing_mode = "auto"
        s.foundry_available = False
        s.video_indexer_available = False
        mock_get_settings.return_value = s
        assert resolve_extraction_mode() == ProcessingMode.LOCAL


# ═══════════════════════════════════════════════════════════
# B. create_extraction_client
# ═══════════════════════════════════════════════════════════


class TestCreateExtractionClient:
    """create_extraction_client: Foundry > Copilot proxy > None."""

    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_foundry_available_returns_foundry(self, mock_get_settings, mock_foundry):
        s = MagicMock()
        s.foundry_available = True
        mock_get_settings.return_value = s
        foundry_client = MagicMock(name="foundry_client")
        mock_foundry.return_value = foundry_client

        assert create_extraction_client() is foundry_client
        mock_foundry.assert_called_once()

    @patch("src.agents.orchestrator.create_copilot_client")
    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_copilot_available_when_foundry_not_returns_copilot(
        self,
        mock_get_settings,
        mock_foundry,
        mock_copilot,
    ):
        s = MagicMock()
        s.foundry_available = False
        s.copilot_proxy_available = True
        s.copilot_proxy_url = "http://localhost:3001"
        s.copilot_proxy_model = "copilot-auto"
        s.copilot_proxy_secret = ""
        mock_get_settings.return_value = s
        copilot_client = MagicMock(name="copilot_client")
        mock_copilot.return_value = copilot_client

        assert create_extraction_client() is copilot_client
        mock_foundry.assert_not_called()

    @patch("src.agents.orchestrator.create_copilot_client")
    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_neither_available_returns_none(self, mock_get_settings, mock_foundry, mock_copilot):
        s = MagicMock()
        s.foundry_available = False
        s.copilot_proxy_available = False
        mock_get_settings.return_value = s

        assert create_extraction_client() is None
        mock_foundry.assert_not_called()
        mock_copilot.assert_not_called()


# ═══════════════════════════════════════════════════════════
# B. create_llm_client
# ═══════════════════════════════════════════════════════════


class TestCreateLlmClient:
    """create_llm_client: downstream client routing by explicit mode and settings."""

    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_explicit_cloud_returns_foundry(self, mock_get_settings, mock_foundry):
        mock_get_settings.return_value = MagicMock()
        foundry_client = MagicMock(name="foundry")
        mock_foundry.return_value = foundry_client

        assert create_llm_client(ProcessingMode.CLOUD) is foundry_client
        mock_foundry.assert_called_once()

    @patch("src.agents.orchestrator.create_copilot_client")
    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_explicit_local_with_copilot_returns_copilot(self, mock_get_settings, mock_foundry, mock_copilot):
        s = MagicMock()
        s.copilot_proxy_available = True
        s.copilot_proxy_url = "http://localhost:3001"
        s.copilot_proxy_model = "copilot-auto"
        s.copilot_proxy_secret = ""
        mock_get_settings.return_value = s
        copilot_client = MagicMock(name="copilot")
        mock_copilot.return_value = copilot_client

        assert create_llm_client(ProcessingMode.LOCAL) is copilot_client
        mock_foundry.assert_not_called()

    @patch("src.agents.orchestrator.create_copilot_client")
    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_explicit_local_no_copilot_falls_back_to_foundry(self, mock_get_settings, mock_foundry, mock_copilot):
        s = MagicMock()
        s.copilot_proxy_available = False
        mock_get_settings.return_value = s
        foundry_client = MagicMock(name="foundry")
        mock_foundry.return_value = foundry_client

        assert create_llm_client(ProcessingMode.LOCAL) is foundry_client
        mock_copilot.assert_not_called()

    @patch("src.agents.orchestrator.create_copilot_client")
    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_no_mode_auto_with_copilot_returns_copilot(self, mock_get_settings, mock_foundry, mock_copilot):
        s = MagicMock()
        s.processing_mode = "auto"
        s.copilot_proxy_available = True
        s.copilot_proxy_url = "http://localhost:3001"
        s.copilot_proxy_model = "copilot-auto"
        s.copilot_proxy_secret = ""
        mock_get_settings.return_value = s
        copilot_client = MagicMock(name="copilot")
        mock_copilot.return_value = copilot_client

        assert create_llm_client() is copilot_client
        mock_foundry.assert_not_called()

    @patch("src.agents.orchestrator.create_copilot_client")
    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.get_settings")
    def test_no_mode_auto_without_copilot_returns_foundry(self, mock_get_settings, mock_foundry, mock_copilot):
        s = MagicMock()
        s.processing_mode = "auto"
        s.copilot_proxy_available = False
        mock_get_settings.return_value = s
        foundry_client = MagicMock(name="foundry")
        mock_foundry.return_value = foundry_client

        assert create_llm_client() is foundry_client
        mock_copilot.assert_not_called()
