"""Resource path resolution for both development and PyInstaller-frozen modes."""

from __future__ import annotations

import sys
from pathlib import Path


def get_resource_base() -> Path:
    """Return the base directory for resource files (prompts, templates).

    In development mode, this is the `src/` directory.
    When frozen by PyInstaller, this is the temporary extraction directory.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "src"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def get_prompts_dir() -> Path:
    """Return the path to the prompts directory."""
    return get_resource_base() / "prompts"


def get_templates_dir() -> Path:
    """Return the path to the templates directory."""
    return get_resource_base() / "templates"
