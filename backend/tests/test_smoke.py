"""Smoke test to verify project structure."""


def test_imports():
    """Verify core packages can be imported."""
    import pydantic
    import structlog

    assert pydantic.VERSION
    assert structlog.__version__
