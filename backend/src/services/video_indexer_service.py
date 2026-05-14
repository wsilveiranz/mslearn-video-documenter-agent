"""Azure Video Indexer client for cloud-mode video analysis.

Handles the full lifecycle: ARM token exchange, video upload, indexing,
insights retrieval, keyframe download, and mapping to ExtractionResult.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from src.config import Settings, get_settings
from src.models.video import (
    BoundingBox,
    Entity,
    ExtractionResult,
    Keyframe,
    OCREntry,
    ProcessingMode,
    Scene,
    TranscriptSegment,
    VideoMetadata,
)
from src.utils.url import url_join

logger = structlog.get_logger()

VI_API_BASE = "https://api.videoindexer.ai"
ARM_TOKEN_SCOPE = "https://management.azure.com/.default"
ARM_API_VERSION = "2024-01-01"

# Refresh tokens 5 minutes before they expire
_TOKEN_REFRESH_MARGIN_S = 300


def _parse_vi_time(time_str: str) -> float:
    """Parse Video Indexer time string to seconds.

    Formats: ``"0:00:01.5"``, ``"0:01:30"``, ``"1:30:00.123"``
    """
    parts = time_str.split(":")
    if len(parts) != 3:
        raise ValueError(f"Unexpected VI time format: {time_str!r}")
    hours, minutes = int(parts[0]), int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


class VideoIndexerService:
    """Azure Video Indexer client for cloud-mode video analysis."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._account_id = settings.video_indexer_account_id
        self._resource_id = settings.video_indexer_resource_id
        self._location = settings.video_indexer_location
        self._credential = settings.get_azure_credential()
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

        # Token cache
        self._access_token: str | None = None
        self._token_expiry: float = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> VideoIndexerService:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_client.aclose()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def get_access_token(self) -> str:
        """Get a Video Indexer account-level access token.

        Two-step process:
        1. Obtain an ARM token via ``DefaultAzureCredential``.
        2. Exchange it for a VI account access token.

        The token is cached and refreshed automatically.
        """
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        logger.info("vi.token_exchange_started")

        # Step 1 — ARM token (sync SDK call, offloaded to thread)
        arm_token_obj = await asyncio.to_thread(
            self._credential.get_token, ARM_TOKEN_SCOPE
        )
        arm_token = arm_token_obj.token

        # Step 2 — Exchange for VI access token
        url = (
            f"{url_join('https://management.azure.com', self._resource_id, 'generateAccessToken')}"
            f"?api-version={ARM_API_VERSION}"
        )
        try:
            response = await self._http_client.post(
                url,
                headers={
                    "Authorization": f"Bearer {arm_token}",
                    "Content-Type": "application/json",
                },
                json={"permissionType": "Contributor", "scope": "Account"},
            )
            if response.status_code != 200:
                logger.error(
                    "vi.token_exchange_failed",
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise RuntimeError(
                    f"VI token exchange failed: {response.status_code}"
                )
        except httpx.ConnectError as exc:
            logger.error("vi.arm_unreachable", error=str(exc))
            raise

        data = response.json()
        self._access_token = data["accessToken"]
        # VI tokens last ~1 hour; refresh with margin
        self._token_expiry = time.time() + 3600 - _TOKEN_REFRESH_MARGIN_S

        logger.info("vi.token_exchange_completed")
        return self._access_token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Video lifecycle
    # ------------------------------------------------------------------

    async def upload_video(
        self,
        video_url: str,
        video_id: str,
        video_name: str | None = None,
    ) -> str:
        """Upload / submit a video for indexing via URL.

        Returns the Video Indexer video ID.
        """
        token = await self.get_access_token()
        name = video_name or video_id

        url = f"{VI_API_BASE}/{self._location}/Accounts/{self._account_id}/Videos"
        params = {
            "accessToken": token,
            "name": name,
            "videoUrl": video_url,
            "privacy": "Private",
            "language": "en-US",
        }

        logger.info("vi.upload_started", video_id=video_id, name=name)

        try:
            response = await self._http_client.post(url, params=params)
            if response.status_code != 200:
                logger.error(
                    "vi.upload_failed",
                    video_id=video_id,
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise RuntimeError(
                    f"Video Indexer upload failed: {response.status_code}"
                )
        except httpx.ConnectError as exc:
            logger.error("vi.unreachable", video_id=video_id, error=str(exc))
            raise

        vi_video_id: str = response.json()["id"]
        logger.info(
            "vi.upload_completed",
            video_id=video_id,
            vi_video_id=vi_video_id,
        )
        return vi_video_id

    async def wait_for_index(
        self,
        vi_video_id: str,
        *,
        timeout_s: float = 600,
        poll_interval_s: float = 15,
        progress_interval_s: float = 30,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Poll until video indexing reaches a terminal state.

        Args:
            vi_video_id: The Video Indexer video ID.
            timeout_s: Maximum wait time in seconds.
            poll_interval_s: Seconds between poll requests.
            progress_interval_s: Minimum seconds between progress emissions.
            on_progress: Optional async callback invoked with progress string (e.g. "42%").

        Returns ``"Processed"`` on success.

        Raises:
            TimeoutError: If indexing exceeds *timeout_s*.
            RuntimeError: If the indexing state becomes ``"Failed"``.
        """
        logger.info("vi.indexing_wait_started", vi_video_id=vi_video_id, timeout_s=timeout_s)
        last_progress = ""
        last_progress_time = 0.0
        start_time = time.time()

        deadline = start_time + timeout_s
        while True:
            token = await self.get_access_token()
            url = (
                f"{VI_API_BASE}/{self._location}/Accounts/{self._account_id}"
                f"/Videos/{vi_video_id}/Index"
            )
            response = await self._http_client.get(
                url, params={"accessToken": token}
            )
            if response.status_code != 200:
                logger.warning(
                    "vi.index_poll_error",
                    vi_video_id=vi_video_id,
                    status=response.status_code,
                )
            else:
                data = response.json()
                state = data.get("state", "Unknown")
                progress = data.get("processingProgress", "")
                logger.debug(
                    "vi.index_poll",
                    vi_video_id=vi_video_id,
                    state=state,
                    progress=progress,
                )

                if state == "Processed":
                    logger.info("vi.indexing_completed", vi_video_id=vi_video_id)
                    return state
                if state == "Failed":
                    failure = data.get("failureCode", "Unknown")
                    logger.error(
                        "vi.indexing_failed",
                        vi_video_id=vi_video_id,
                        failure_code=failure,
                    )
                    raise RuntimeError(
                        f"Video Indexer indexing failed: {failure}"
                    )

                if on_progress:
                    now = time.time()
                    progress_changed = progress and progress != last_progress
                    time_to_emit = (now - last_progress_time) >= progress_interval_s

                    if progress_changed or time_to_emit:
                        last_progress_time = now
                        if progress:
                            await on_progress(progress)
                        else:
                            await on_progress("Processing...")

                # Track latest progress value
                if progress and progress != last_progress:
                    last_progress = progress

            if time.time() >= deadline:
                raise TimeoutError(
                    f"Video indexing timed out after {timeout_s}s "
                    f"(vi_video_id={vi_video_id})"
                )
            await asyncio.sleep(poll_interval_s)

    # ------------------------------------------------------------------
    # Insights retrieval
    # ------------------------------------------------------------------

    async def get_insights(self, vi_video_id: str) -> dict:
        """Retrieve the full insights JSON for a processed video."""
        token = await self.get_access_token()
        url = (
            f"{VI_API_BASE}/{self._location}/Accounts/{self._account_id}"
            f"/Videos/{vi_video_id}/Index"
        )

        response = await self._http_client.get(
            url, params={"accessToken": token}
        )
        if response.status_code != 200:
            logger.error(
                "vi.get_insights_failed",
                vi_video_id=vi_video_id,
                status=response.status_code,
                body=response.text[:500],
            )
            raise RuntimeError(
                f"Failed to get insights: {response.status_code}"
            )

        logger.info("vi.insights_retrieved", vi_video_id=vi_video_id)
        return response.json()

    # ------------------------------------------------------------------
    # Keyframe thumbnails
    # ------------------------------------------------------------------

    async def download_keyframe_thumbnails(
        self,
        vi_video_id: str,
        insights: dict,
        output_dir: str | Path,
    ) -> list[Path]:
        """Download keyframe thumbnail images from Video Indexer.

        Iterates over shots → keyFrames in the insights JSON and saves
        each thumbnail to *output_dir* as ``kf_NNN.jpg``.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        token = await self.get_access_token()
        video_insights = insights.get("videos", [{}])[0].get("insights", {})
        shots = video_insights.get("shots", [])

        paths: list[Path] = []
        idx = 0
        for shot in shots:
            for kf in shot.get("keyFrames", []):
                for inst in kf.get("instances", []):
                    thumbnail_id = inst.get("thumbnailId")
                    if not thumbnail_id:
                        continue

                    thumb_url = (
                        f"{VI_API_BASE}/{self._location}/Accounts/{self._account_id}"
                        f"/Videos/{vi_video_id}/Thumbnails/{thumbnail_id}"
                    )
                    try:
                        resp = await self._http_client.get(
                            thumb_url,
                            params={"accessToken": token, "format": "Jpeg"},
                        )
                        if resp.status_code != 200:
                            logger.warning(
                                "vi.thumbnail_download_failed",
                                vi_video_id=vi_video_id,
                                thumbnail_id=thumbnail_id,
                                status=resp.status_code,
                            )
                            continue
                    except httpx.ConnectError as exc:
                        logger.warning(
                            "vi.thumbnail_unreachable",
                            vi_video_id=vi_video_id,
                            thumbnail_id=thumbnail_id,
                            error=str(exc),
                        )
                        continue

                    dest = output_path / f"kf_{idx:03d}.jpg"
                    dest.write_bytes(resp.content)
                    paths.append(dest)
                    idx += 1

        logger.info(
            "vi.thumbnails_downloaded",
            vi_video_id=vi_video_id,
            count=len(paths),
        )
        return paths

    # ------------------------------------------------------------------
    # Insights → ExtractionResult mapping
    # ------------------------------------------------------------------

    def map_to_extraction_result(
        self,
        insights: dict,
        keyframe_paths: list[Path],
        video_metadata: VideoMetadata,
    ) -> ExtractionResult:
        """Map Video Indexer insights JSON to our ``ExtractionResult`` schema."""
        video_insights = insights.get("videos", [{}])[0].get("insights", {})

        # Build speaker lookup
        speakers: dict[int, str] = {}
        for spk in video_insights.get("speakers", []):
            speakers[spk["id"]] = spk.get("name", f"Speaker {spk['id']}")

        transcript = self._map_transcript(video_insights, speakers)
        keyframes = self._map_keyframes(video_insights, keyframe_paths)
        scenes = self._map_scenes(video_insights, keyframes)
        ocr_entries = self._map_ocr(video_insights)
        entities = self._map_entities(video_insights)

        logger.info(
            "vi.mapping_completed",
            transcript_segments=len(transcript),
            scenes=len(scenes),
            keyframes=len(keyframes),
            ocr_entries=len(ocr_entries),
            entities=len(entities),
        )

        return ExtractionResult(
            transcript=transcript,
            scenes=scenes,
            keyframes=keyframes,
            ocr_entries=ocr_entries,
            entities=entities,
            video_metadata=video_metadata,
            processing_mode=ProcessingMode.CLOUD,
        )

    # ------------------------------------------------------------------
    # Private mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_transcript(
        video_insights: dict,
        speakers: dict[int, str],
    ) -> list[TranscriptSegment]:
        segments: list[TranscriptSegment] = []
        for entry in video_insights.get("transcript", []):
            instances = entry.get("instances", [])
            if not instances:
                continue
            inst = instances[0]
            speaker_id = entry.get("speakerId")
            segments.append(
                TranscriptSegment(
                    text=entry.get("text", ""),
                    start_seconds=_parse_vi_time(inst["start"]),
                    end_seconds=_parse_vi_time(inst["end"]),
                    speaker=speakers.get(speaker_id) if speaker_id is not None else None,
                    confidence=entry.get("confidence", 1.0),
                )
            )
        return segments

    @staticmethod
    def _map_keyframes(
        video_insights: dict,
        keyframe_paths: list[Path],
    ) -> list[Keyframe]:
        keyframes: list[Keyframe] = []
        idx = 0
        for shot in video_insights.get("shots", []):
            for kf in shot.get("keyFrames", []):
                for inst in kf.get("instances", []):
                    image_path = str(keyframe_paths[idx]) if idx < len(keyframe_paths) else ""
                    keyframes.append(
                        Keyframe(
                            id=f"kf_{idx:03d}",
                            timestamp_seconds=_parse_vi_time(inst["start"]),
                            image_path=image_path,
                        )
                    )
                    idx += 1
        return keyframes

    @staticmethod
    def _map_scenes(
        video_insights: dict,
        keyframes: list[Keyframe],
    ) -> list[Scene]:
        scenes: list[Scene] = []
        for entry in video_insights.get("scenes", []):
            instances = entry.get("instances", [])
            if not instances:
                continue
            inst = instances[0]
            scene_start = _parse_vi_time(inst["start"])
            scene_end = _parse_vi_time(inst["end"])
            scene_id = f"scene_{entry['id']:03d}"

            # Link keyframes that fall within this scene's time range
            linked_kf_ids: list[str] = []
            for kf in keyframes:
                if scene_start <= kf.timestamp_seconds <= scene_end:
                    linked_kf_ids.append(kf.id)
                    kf.scene_id = scene_id

            scenes.append(
                Scene(
                    id=scene_id,
                    start_seconds=scene_start,
                    end_seconds=scene_end,
                    keyframe_ids=linked_kf_ids,
                )
            )
        return scenes

    @staticmethod
    def _map_ocr(video_insights: dict) -> list[OCREntry]:
        entries: list[OCREntry] = []
        for item in video_insights.get("ocr", []):
            instances = item.get("instances", [])
            if not instances:
                continue
            timestamp = _parse_vi_time(instances[0]["start"])

            bbox: BoundingBox | None = None
            if all(k in item for k in ("left", "top", "width", "height")):
                bbox = BoundingBox(
                    x=item["left"],
                    y=item["top"],
                    width=item["width"],
                    height=item["height"],
                )

            entries.append(
                OCREntry(
                    text=item.get("text", ""),
                    timestamp_seconds=timestamp,
                    bounding_box=bbox,
                    confidence=item.get("confidence", 1.0),
                )
            )
        return entries

    @staticmethod
    def _map_entities(video_insights: dict) -> list[Entity]:
        entities: list[Entity] = []

        entity_sources = [
            ("brands", "brand"),
            ("namedPeople", "person"),
            ("namedLocations", "location"),
        ]
        for key, entity_type in entity_sources:
            for item in video_insights.get(key, []):
                mentions = [
                    _parse_vi_time(inst["start"])
                    for inst in item.get("instances", [])
                    if "start" in inst
                ]
                entities.append(
                    Entity(
                        name=item.get("name", ""),
                        entity_type=entity_type,
                        mentions=mentions,
                    )
                )
        return entities

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def delete_video(self, vi_video_id: str) -> None:
        """Delete a video from Video Indexer."""
        token = await self.get_access_token()
        url = (
            f"{VI_API_BASE}/{self._location}/Accounts/{self._account_id}"
            f"/Videos/{vi_video_id}"
        )

        try:
            response = await self._http_client.delete(
                url, params={"accessToken": token}
            )
            if response.status_code not in (200, 204):
                logger.warning(
                    "vi.delete_failed",
                    vi_video_id=vi_video_id,
                    status=response.status_code,
                )
                return
        except httpx.ConnectError as exc:
            logger.warning(
                "vi.delete_unreachable",
                vi_video_id=vi_video_id,
                error=str(exc),
            )
            return

        logger.info("vi.video_deleted", vi_video_id=vi_video_id)
