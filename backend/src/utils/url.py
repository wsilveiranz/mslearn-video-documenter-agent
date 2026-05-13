"""URL construction utilities."""

from __future__ import annotations


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
