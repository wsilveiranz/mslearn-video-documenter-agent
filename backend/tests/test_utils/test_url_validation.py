"""Tests for validate_blob_url utility."""

from __future__ import annotations

import pytest

from src.utils.url import validate_blob_url

ACCOUNT_URL = "https://myaccount.blob.core.windows.net"
CONTAINER = "video-documenter"


class TestValidateBlobUrl:
    """Tests for validate_blob_url."""

    def test_valid_url_returns_blob_name(self) -> None:
        url = "https://myaccount.blob.core.windows.net/video-documenter/abc123/demo.mp4"
        result = validate_blob_url(url, ACCOUNT_URL, CONTAINER)
        assert result == "abc123/demo.mp4"

    def test_valid_url_single_segment_blob_name(self) -> None:
        url = "https://myaccount.blob.core.windows.net/video-documenter/file.mp4"
        result = validate_blob_url(url, ACCOUNT_URL, CONTAINER)
        assert result == "file.mp4"

    def test_wrong_account_host_raises(self) -> None:
        url = "https://otheraccount.blob.core.windows.net/video-documenter/abc/demo.mp4"
        with pytest.raises(ValueError, match="does not match expected account host"):
            validate_blob_url(url, ACCOUNT_URL, CONTAINER)

    def test_wrong_container_raises(self) -> None:
        url = "https://myaccount.blob.core.windows.net/wrong-container/abc/demo.mp4"
        with pytest.raises(ValueError, match="does not match expected container"):
            validate_blob_url(url, ACCOUNT_URL, CONTAINER)

    def test_missing_blob_path_raises(self) -> None:
        url = "https://myaccount.blob.core.windows.net/video-documenter"
        with pytest.raises(ValueError, match="no blob path after container"):
            validate_blob_url(url, ACCOUNT_URL, CONTAINER)

    def test_missing_blob_path_trailing_slash_raises(self) -> None:
        url = "https://myaccount.blob.core.windows.net/video-documenter/"
        with pytest.raises(ValueError, match="no blob path after container"):
            validate_blob_url(url, ACCOUNT_URL, CONTAINER)

    def test_url_with_sas_query_params(self) -> None:
        url = (
            "https://myaccount.blob.core.windows.net/video-documenter/vid/file.mp4"
            "?sv=2023-01-01&st=2024-01-01&se=2025-01-01&sr=b&sp=r&sig=abc123"
        )
        result = validate_blob_url(url, ACCOUNT_URL, CONTAINER)
        assert result == "vid/file.mp4"

    def test_case_insensitive_host_comparison(self) -> None:
        url = "https://MyAccount.Blob.Core.Windows.Net/video-documenter/abc/demo.mp4"
        result = validate_blob_url(url, ACCOUNT_URL, CONTAINER)
        assert result == "abc/demo.mp4"

    def test_case_insensitive_account_url(self) -> None:
        url = "https://myaccount.blob.core.windows.net/video-documenter/abc/demo.mp4"
        result = validate_blob_url(url, "https://MYACCOUNT.BLOB.CORE.WINDOWS.NET", CONTAINER)
        assert result == "abc/demo.mp4"

    def test_case_insensitive_container_comparison(self) -> None:
        url = "https://myaccount.blob.core.windows.net/Video-Documenter/abc/demo.mp4"
        result = validate_blob_url(url, ACCOUNT_URL, "video-documenter")
        assert result == "abc/demo.mp4"

    def test_percent_encoded_blob_name_decoded(self) -> None:
        url = "https://myaccount.blob.core.windows.net/video-documenter/My%20Demo/file%20name.mp4"
        result = validate_blob_url(url, ACCOUNT_URL, CONTAINER)
        assert result == "My Demo/file name.mp4"

    def test_percent_encoded_special_chars(self) -> None:
        url = "https://myaccount.blob.core.windows.net/video-documenter/vid%2B1/demo%23v2.mp4"
        result = validate_blob_url(url, ACCOUNT_URL, CONTAINER)
        assert result == "vid+1/demo#v2.mp4"

    def test_rejects_userinfo_in_url(self) -> None:
        url = "https://attacker.com@myaccount.blob.core.windows.net/video-documenter/file.mp4"
        with pytest.raises(ValueError, match="must not contain credentials"):
            validate_blob_url(url, ACCOUNT_URL, CONTAINER)
