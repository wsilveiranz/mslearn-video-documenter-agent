"""GPT-4o Vision analysis service for keyframe screenshot understanding."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from agent_framework import Content, Message
from agent_framework.foundry import FoundryChatClient

from src.models.video import Keyframe

logger = structlog.get_logger()

VISION_SYSTEM_PROMPT = """You are a UI analysis expert for screen recording documentation.

Analyze the screenshot and describe:
1. What application or page is visible
2. What UI elements are highlighted, selected, or active
3. What action the user appears to be performing
4. Any text visible on screen (menus, buttons, labels, code)

Be specific and factual. Focus on what is visible, not what you assume.
Format your response as a concise paragraph (2-4 sentences)."""

_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class VisionService:
    """Analyzes keyframe screenshots using GPT-4o Vision via Azure AI Foundry."""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_keyframe(
        self,
        image_path: str | Path,
        client: FoundryChatClient,
    ) -> str:
        """Analyze a single keyframe image and return a UI state description.

        Args:
            image_path: Path to the keyframe image file.
            client: FoundryChatClient instance for GPT-4o Vision calls.

        Returns:
            A concise description of the UI state shown in the image.
        """
        image_path = Path(image_path)
        suffix = image_path.suffix.lower()
        mime_type = _MIME_TYPES.get(suffix, "image/png")

        image_bytes = image_path.read_bytes()

        messages: list[Message] = [
            Message("system", [Content.from_text(VISION_SYSTEM_PROMPT)]),
            Message(
                "user",
                [
                    Content.from_data(image_bytes, mime_type),
                    Content.from_text("Describe the UI state shown in this screenshot."),
                ],
            ),
        ]

        async with self._semaphore:
            logger.debug(
                "analyzing_keyframe",
                operation="vision_analyze",
                image_path=image_path.name,
                mime_type=mime_type,
            )
            response = await client.get_response(messages=messages)

        description: str = response.text or ""
        logger.info(
            "keyframe_analyzed",
            operation="vision_analyze",
            image_path=image_path.name,
            description_length=len(description),
        )
        return description

    async def analyze_keyframes(
        self,
        keyframes: list[Keyframe],
        client: FoundryChatClient,
    ) -> list[Keyframe]:
        """Analyze all keyframes concurrently (rate-limited by semaphore).

        Args:
            keyframes: List of Keyframe objects with image_path set.
            client: FoundryChatClient instance for GPT-4o Vision calls.

        Returns:
            Updated keyframe list with ui_description populated on each frame.
        """

        async def _analyze_one(keyframe: Keyframe) -> Keyframe:
            try:
                keyframe.ui_description = await self.analyze_keyframe(
                    keyframe.image_path, client
                )
            except Exception as exc:
                logger.warning(
                    "keyframe_analysis_failed",
                    operation="vision_analyze",
                    keyframe_id=keyframe.id,
                    timestamp_seconds=keyframe.timestamp_seconds,
                    error=str(exc),
                )
                keyframe.ui_description = ""
            return keyframe

        updated = await asyncio.gather(*[_analyze_one(kf) for kf in keyframes])
        logger.info(
            "keyframes_analyzed",
            operation="vision_analyze_batch",
            total=len(keyframes),
            succeeded=sum(1 for kf in updated if kf.ui_description),
        )
        return list(updated)
