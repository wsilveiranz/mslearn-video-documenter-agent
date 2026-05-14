"""URL construction and validation utilities."""

from __future__ import annotations

from urllib.parse import urlparse


def validate_blob_url(blob_url: str, account_url: str, container_name: str) -> str:
    """Validate a blob URL matches the expected account and container, and return the blob name.

    Args:
        blob_url: Full Azure Blob Storage URL
            (e.g., https://account.blob.core.windows.net/container/path/file.mp4).
        account_url: Expected account URL from settings
            (e.g., https://account.blob.core.windows.net).
        container_name: Expected container name from settings.

    Returns:
        The blob name (path after the container segment).

    Raises:
        ValueError: If the URL host doesn't match the account or the container doesn't match.
    """
    parsed_blob = urlparse(blob_url)
    parsed_account = urlparse(account_url)

    if (parsed_blob.hostname or "").lower() != (parsed_account.hostname or "").lower():
        raise ValueError(
            f"Blob URL host '{parsed_blob.hostname}' does not match "
            f"expected account host '{parsed_account.hostname}'. "
            f"Blob URL: {blob_url}, Account URL: {account_url}"
        )

    path_segments = parsed_blob.path.lstrip("/").split("/", 1)
    url_container = path_segments[0] if path_segments else ""

    if url_container != container_name:
        raise ValueError(
            f"Blob URL container '{url_container}' does not match "
            f"expected container '{container_name}'. Blob URL: {blob_url}"
        )

    if len(path_segments) < 2 or not path_segments[1]:
        raise ValueError(
            f"Blob URL has no blob path after container '{container_name}'. "
            f"Blob URL: {blob_url}"
        )

    return path_segments[1]


def url_join(base: str, *segments: str) -> str:
    """Join a base URL with path segments, normalizing slashes.

    Handles trailing slashes on base and leading/trailing slashes on segments
    to prevent double-slash issues in constructed URLs.

    Examples:
        >>> url_join("https://example.com/", "container", "blob")
        'https://example.com/container/blob'
        >>> url_join("https://example.com", "/path/", "/file")
        'https://example.com/path/file'
    """
    result = base.rstrip("/")
    for segment in segments:
        result = result + "/" + segment.strip("/")
    return result
