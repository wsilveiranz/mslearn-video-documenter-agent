"""Shared pytest fixtures and markers for the test suite."""

from __future__ import annotations

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "cloud: tests requiring Azure cloud services")
    config.addinivalue_line("markers", "local: tests for local-mode processing")
    config.addinivalue_line("markers", "integration: integration tests requiring external services")
    config.addinivalue_line("markers", "slow: slow tests (>10s)")
