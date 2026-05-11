"""Unit tests for the pipeline orchestrator with all agents mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.orchestrator import PipelineInput, PipelineResult, run_pipeline
from src.models.document import (
    DocType,
    DocumentOutline,
    DocumentSection,
    Frontmatter,
    GeneratedDocument,
)
from src.models.evaluation import EvaluationReport, EvaluationScores
from src.models.video import (
    ExtractionResult,
    IngestionResult,
    ProcessingMode,
    TranscriptSegment,
    VideoMetadata,
    VideoSourceType,
)


def _make_metadata() -> VideoMetadata:
    return VideoMetadata(
        video_id="vid001",
        source_path="/fake/video.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=60.0,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=1024,
    )


def _make_ingestion_result() -> IngestionResult:
    return IngestionResult(
        video_id="vid001",
        metadata=_make_metadata(),
        processing_mode=ProcessingMode.LOCAL,
    )


def _make_extraction_result() -> ExtractionResult:
    return ExtractionResult(
        video_metadata=_make_metadata(),
        processing_mode=ProcessingMode.LOCAL,
        transcript=[
            TranscriptSegment(text="This is a test transcript.", start_seconds=0.0, end_seconds=5.0),
        ],
    )


def _make_outline() -> DocumentOutline:
    return DocumentOutline(
        doc_type=DocType.TUTORIAL,
        frontmatter=Frontmatter(title="Test tutorial", description="A test tutorial for unit tests."),
        sections=[DocumentSection(heading="Introduction", level=2)],
    )


def _make_document() -> GeneratedDocument:
    return GeneratedDocument(
        document_id="doc001",
        doc_type=DocType.TUTORIAL,
        outline=_make_outline(),
        markdown_content="# Tutorial\n\nContent here.",
        word_count=3,
    )


def _make_evaluation(passed: bool = True) -> EvaluationReport:
    return EvaluationReport(
        document_id="doc001",
        scores=EvaluationScores(
            completeness=0.9,
            accuracy=0.9,
            style_compliance=0.9,
            readability=0.9,
        ),
        passed=passed,
        suggestions=[],
        summary="Good quality.",
    )


class TestRunPipeline:
    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.EvaluateAgent")
    @patch("src.agents.orchestrator.EditorAgent")
    @patch("src.agents.orchestrator.WriterAgent")
    @patch("src.agents.orchestrator.StructureAgent")
    @patch("src.agents.orchestrator.ExtractionAgent")
    @patch("src.agents.orchestrator.IngestionAgent")
    @patch("src.agents.orchestrator.get_settings")
    async def test_pipeline_executes_all_stages(
        self,
        mock_settings,
        mock_ingestion_cls,
        mock_extraction_cls,
        mock_structure_cls,
        mock_writer_cls,
        mock_editor_cls,
        mock_evaluate_cls,
        mock_create_client,
    ):
        """Test that all 6 pipeline stages execute in order."""
        # Settings — use cloud mode so pipeline always routes to Foundry client
        settings = MagicMock()
        settings.processing_mode = "cloud"
        settings.copilot_proxy_url = ""
        mock_settings.return_value = settings

        # Foundry client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock each agent
        ingestion = MagicMock()
        ingestion.process = AsyncMock(return_value=_make_ingestion_result())
        mock_ingestion_cls.return_value = ingestion

        extraction = MagicMock()
        extraction.process = AsyncMock(return_value=_make_extraction_result())
        mock_extraction_cls.return_value = extraction

        structure = MagicMock()
        structure.process = AsyncMock(return_value=_make_outline())
        mock_structure_cls.return_value = structure

        writer = MagicMock()
        writer.process = AsyncMock(return_value=_make_document())
        mock_writer_cls.return_value = writer

        editor = MagicMock()
        editor.process = AsyncMock(return_value=_make_document())
        mock_editor_cls.return_value = editor

        evaluate = MagicMock()
        evaluate.process = AsyncMock(return_value=_make_evaluation(passed=True))
        mock_evaluate_cls.return_value = evaluate

        # Run pipeline
        request = PipelineInput(video_source="/fake/video.mp4", doc_type=DocType.TUTORIAL)
        events = await run_pipeline.run(request)
        result = events[-1].data

        # Verify all stages were called
        ingestion.process.assert_awaited_once()
        extraction.process.assert_awaited_once()
        structure.process.assert_awaited_once()
        writer.process.assert_awaited_once()
        editor.process.assert_awaited_once()
        evaluate.process.assert_awaited_once()

        # Verify result
        assert isinstance(result, PipelineResult)
        assert result.document.document_id == "doc001"
        assert result.evaluation.passed is True

        # Verify ExtractionAgent received the foundry client
        mock_extraction_cls.assert_called_once_with(foundry_client=mock_client)

    @patch("src.agents.orchestrator.create_foundry_client")
    @patch("src.agents.orchestrator.EvaluateAgent")
    @patch("src.agents.orchestrator.EditorAgent")
    @patch("src.agents.orchestrator.WriterAgent")
    @patch("src.agents.orchestrator.StructureAgent")
    @patch("src.agents.orchestrator.ExtractionAgent")
    @patch("src.agents.orchestrator.IngestionAgent")
    @patch("src.agents.orchestrator.get_settings")
    async def test_pipeline_revision_loop(
        self,
        mock_settings,
        mock_ingestion_cls,
        mock_extraction_cls,
        mock_structure_cls,
        mock_writer_cls,
        mock_editor_cls,
        mock_evaluate_cls,
        mock_create_client,
    ):
        """Test that the pipeline re-edits when evaluation fails."""
        settings = MagicMock()
        settings.processing_mode = "cloud"
        settings.copilot_proxy_url = ""
        mock_settings.return_value = settings
        mock_create_client.return_value = MagicMock()

        mock_ingestion_cls.return_value.process = AsyncMock(return_value=_make_ingestion_result())
        mock_extraction_cls.return_value.process = AsyncMock(return_value=_make_extraction_result())
        mock_structure_cls.return_value.process = AsyncMock(return_value=_make_outline())
        mock_writer_cls.return_value.process = AsyncMock(return_value=_make_document())

        editor_mock = MagicMock()
        editor_mock.process = AsyncMock(return_value=_make_document())
        mock_editor_cls.return_value = editor_mock

        # First evaluation fails, second passes
        eval_mock = MagicMock()
        eval_mock.process = AsyncMock(
            side_effect=[_make_evaluation(passed=False), _make_evaluation(passed=True)]
        )
        mock_evaluate_cls.return_value = eval_mock

        request = PipelineInput(video_source="/fake/video.mp4", doc_type=DocType.TUTORIAL)
        events = await run_pipeline.run(request)
        result = events[-1].data

        assert result.evaluation.passed is True
        # Editor called twice: initial + one revision
        assert editor_mock.process.await_count == 2
        # Evaluate called twice
        assert eval_mock.process.await_count == 2
