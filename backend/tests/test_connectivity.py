"""Phase 0 connectivity and smoke tests.

Run all tests:
    pytest tests/test_connectivity.py -v

Run only tests that don't require Azure:
    pytest tests/test_connectivity.py -v -m "not cloud"

Run only cloud connectivity tests:
    pytest tests/test_connectivity.py -v -m cloud

Run only local-mode tests:
    pytest tests/test_connectivity.py -v -m local
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

# ═══════════════════════════════════════════════════════════
# 1. CONFIGURATION TESTS (always run)
# ═══════════════════════════════════════════════════════════

class TestConfiguration:
    """Verify configuration module loads correctly."""

    def test_settings_load(self):
        """Settings can be loaded with defaults."""
        from src.config import Settings
        settings = Settings()
        assert settings.processing_mode in ("cloud", "local")
        assert settings.foundry_model  # just verify it's set
        assert settings.blob_container_name == "video-documenter"

    def test_settings_cloud_mode_properties(self):
        """Cloud/local mode properties work correctly."""
        from src.config import Settings
        cloud = Settings(processing_mode="cloud")
        assert cloud.is_cloud_mode is True
        assert cloud.is_local_mode is False

        local = Settings(processing_mode="local")
        assert local.is_cloud_mode is False
        assert local.is_local_mode is True

    def test_get_settings_cached(self):
        """get_settings returns cached instance."""
        from src.config import get_settings
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


# ═══════════════════════════════════════════════════════════
# 2. IMPORT TESTS (always run)
# ═══════════════════════════════════════════════════════════

class TestImports:
    """Verify all project modules can be imported."""

    @pytest.mark.parametrize("module_path", [
        "src.models.video",
        "src.models.document",
        "src.models.evaluation",
        "src.config",
        "src.agents.ingestion",
        "src.agents.extraction",
        "src.agents.structure",
        "src.agents.writer",
        "src.agents.editor",
        "src.agents.evaluate",
        "src.agents.orchestrator",
        "src.api.routes",
        "src.api.websocket",
        "src.main",
    ])
    def test_module_imports(self, module_path: str):
        """Each module can be imported without errors."""
        importlib.import_module(module_path)


# ═══════════════════════════════════════════════════════════
# 3. DATA MODEL TESTS (always run)
# ═══════════════════════════════════════════════════════════

class TestDataModels:
    """Verify Pydantic models can be instantiated."""

    def test_video_metadata_creation(self):
        from src.models.video import VideoMetadata, VideoSourceType
        vm = VideoMetadata(
            video_id="test-001",
            source_path="C:\\test\\video.mp4",
            source_type=VideoSourceType.LOCAL_FILE,
            duration_seconds=120.0,
            resolution_width=1920,
            resolution_height=1080,
            fps=30.0,
            file_size_bytes=50_000_000,
        )
        assert vm.video_id == "test-001"
        assert vm.duration_seconds == 120.0

    def test_extraction_result_creation(self):
        from src.models.video import ExtractionResult, ProcessingMode, VideoMetadata, VideoSourceType
        metadata = VideoMetadata(
            video_id="test-002",
            source_path="/test.mp4",
            source_type=VideoSourceType.LOCAL_FILE,
            duration_seconds=60.0,
            resolution_width=1280,
            resolution_height=720,
            fps=24.0,
            file_size_bytes=10_000_000,
        )
        result = ExtractionResult(
            video_metadata=metadata,
            processing_mode=ProcessingMode.LOCAL,
        )
        assert result.transcript == []
        assert result.scenes == []
        assert result.processing_mode == ProcessingMode.LOCAL

    def test_document_outline_creation(self):
        from src.models.document import DocType, DocumentOutline, Frontmatter
        outline = DocumentOutline(
            doc_type=DocType.TUTORIAL,
            frontmatter=Frontmatter(
                title="Tutorial: Deploy a Python web app to Azure App Service",
                description="Learn how to deploy a Python web app to Azure App Service using the Azure CLI.",
            ),
        )
        assert outline.doc_type == DocType.TUTORIAL
        assert len(outline.frontmatter.title) >= 43

    def test_evaluation_scores(self):
        from src.models.evaluation import EvaluationScores
        good = EvaluationScores(completeness=0.9, accuracy=0.85, style_compliance=0.8, readability=0.9)
        assert good.overall == pytest.approx(0.8625)
        assert good.passed is True

        bad = EvaluationScores(completeness=0.4, accuracy=0.3, style_compliance=0.5, readability=0.6)
        assert bad.passed is False

    def test_evaluation_report_creation(self):
        from src.models.evaluation import EvaluationReport, EvaluationScores
        scores = EvaluationScores(completeness=0.8, accuracy=0.7, style_compliance=0.75, readability=0.85)
        report = EvaluationReport(
            document_id="doc-001",
            scores=scores,
            passed=scores.passed,
            summary="Good quality document.",
        )
        assert report.passed is True
        assert report.document_id == "doc-001"


# ═══════════════════════════════════════════════════════════
# 4. AGENT INSTANTIATION TESTS (always run)
# ═══════════════════════════════════════════════════════════

class TestAgentInstantiation:
    """Verify agents can be created (not requiring Azure connection)."""

    def test_ingestion_agent(self):
        from src.agents.ingestion import IngestionAgent
        agent = IngestionAgent()
        assert agent is not None

    def test_extraction_agent(self):
        from src.agents.extraction import ExtractionAgent
        agent = ExtractionAgent()
        assert agent is not None

    def test_source_type_detection(self):
        """Ingestion agent correctly detects video source types."""
        from src.agents.ingestion import IngestionAgent
        from src.models.video import VideoSourceType
        agent = IngestionAgent()

        assert agent._detect_source_type("C:\\videos\\demo.mp4") == VideoSourceType.LOCAL_FILE
        assert agent._detect_source_type("/home/user/demo.mp4") == VideoSourceType.LOCAL_FILE
        assert agent._detect_source_type("https://myaccount.blob.core.windows.net/container/video.mp4") == VideoSourceType.BLOB_URL
        assert agent._detect_source_type("https://www.youtube.com/watch?v=abc") == VideoSourceType.YOUTUBE
        assert agent._detect_source_type("https://youtu.be/abc") == VideoSourceType.YOUTUBE
        assert agent._detect_source_type("https://web.microsoftstream.com/video/abc") == VideoSourceType.STREAM


# ═══════════════════════════════════════════════════════════
# 5. FASTAPI TESTS (always run)
# ═══════════════════════════════════════════════════════════

class TestFastAPI:
    """Verify FastAPI app can be created and routes are registered."""

    def test_app_creation(self):
        from src.main import create_app
        app = create_app()
        assert app.title == "MS Learn Video Documenter Agent"

    def test_health_endpoint(self):
        """Health endpoint returns OK."""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_ingest_requires_input(self):
        """Ingest endpoint validates that file or path is provided."""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        response = client.post("/api/v1/videos/ingest")
        assert response.status_code in (400, 422)

    def test_status_not_found(self):
        """Status endpoint returns 404 for unknown video ID."""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        response = client.get("/api/v1/videos/nonexistent/status")
        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════
# 6. TEMPLATE AND PROMPT TESTS (always run)
# ═══════════════════════════════════════════════════════════

class TestTemplatesAndPrompts:
    """Verify all template and prompt files exist and are non-empty."""

    @pytest.mark.parametrize("template_name", [
        "quickstart.md",
        "tutorial.md",
        "howto.md",
        "concept.md",
        "overview.md",
    ])
    def test_template_exists(self, template_name: str):
        from pathlib import Path
        path = Path(__file__).parent.parent / "src" / "templates" / template_name
        assert path.exists(), f"Template {template_name} not found at {path}"
        content = path.read_text(encoding="utf-8")
        assert len(content) > 100, f"Template {template_name} seems too short"
        assert "---" in content, f"Template {template_name} missing YAML frontmatter"

    @pytest.mark.parametrize("prompt_name", [
        "structure_system.md",
        "writer_system.md",
        "editor_system.md",
        "evaluate_system.md",
    ])
    def test_prompt_exists(self, prompt_name: str):
        from pathlib import Path
        path = Path(__file__).parent.parent / "src" / "prompts" / prompt_name
        assert path.exists(), f"Prompt {prompt_name} not found at {path}"
        content = path.read_text(encoding="utf-8")
        assert len(content) > 200, f"Prompt {prompt_name} seems too short"


# ═══════════════════════════════════════════════════════════
# 7. LOCAL TOOL AVAILABILITY (local mode)
# ═══════════════════════════════════════════════════════════

class TestLocalTools:
    """Verify local processing tools are available."""

    @pytest.mark.local
    def test_ffmpeg_available(self):
        """FFmpeg binary is available on PATH."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError:
            pytest.fail("FFmpeg binary not found on PATH")
        assert result.returncode == 0, f"FFmpeg not found or returned error: {result.stderr}"
        assert "ffmpeg version" in result.stdout.lower()

    @pytest.mark.local
    def test_python_version(self):
        """Python version is 3.11+."""
        assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version}"


# ═══════════════════════════════════════════════════════════
# 8. AZURE CONNECTIVITY (cloud mode — requires credentials)
# ═══════════════════════════════════════════════════════════

class TestAzureConnectivity:
    """Verify Azure services are reachable. Requires az login and provisioned resources."""

    @pytest.mark.cloud
    @pytest.mark.integration
    @pytest.mark.slow
    def test_azure_credential(self):
        """DefaultAzureCredential can obtain a token."""
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        assert token.token, "Failed to get Azure token"

    @pytest.mark.cloud
    @pytest.mark.integration
    @pytest.mark.slow
    def test_foundry_llm_reachable(self):
        """Azure AI Foundry can complete a simple request."""
        from src.config import get_settings
        settings = get_settings()
        if not settings.foundry_project_endpoint:
            pytest.skip("FOUNDRY_PROJECT_ENDPOINT not set")

        import asyncio

        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        client = FoundryChatClient(
            project_endpoint=settings.foundry_project_endpoint,
            model=settings.foundry_model,
            credential=DefaultAzureCredential(),
        )
        agent = Agent(client=client, name="test", instructions="Reply with exactly: PONG")
        result = asyncio.run(agent.run("PING"))
        assert "PONG" in str(result).upper(), f"Unexpected LLM response: {result}"

    @pytest.mark.cloud
    @pytest.mark.integration
    @pytest.mark.slow
    def test_blob_storage_reachable(self):
        """Azure Blob Storage container is accessible."""
        from src.config import get_settings
        settings = get_settings()
        if not settings.blob_account_url:
            pytest.skip("BLOB_ACCOUNT_URL not set")

        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        blob_client = BlobServiceClient(
            account_url=settings.blob_account_url,
            credential=DefaultAzureCredential(),
        )
        container = blob_client.get_container_client(settings.blob_container_name)
        props = container.get_container_properties()
        assert props is not None

    @pytest.mark.cloud
    @pytest.mark.integration
    @pytest.mark.slow
    def test_speech_service_reachable(self):
        """Azure AI Speech service endpoint is reachable."""
        from src.config import get_settings
        settings = get_settings()
        if not settings.speech_service_endpoint:
            pytest.skip("SPEECH_SERVICE_ENDPOINT not set")

        import httpx
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")

        response = httpx.get(
            f"{settings.speech_service_endpoint.rstrip('/')}/speechtotext/v3.2/models",
            headers={"Authorization": f"Bearer {token.token}"},
            timeout=10,
        )
        # 200 or 403 both mean the service is reachable
        assert response.status_code in (200, 401, 403), (
            f"Speech service unreachable: {response.status_code}"
        )
