"Tests for settings validation."

from __future__ import annotations

from pathlib import Path

import pytest

from acr_push_tui.settings import AppSettings


def test_require_ci_fields_missing() -> None:
    settings = AppSettings()
    with pytest.raises(ValueError):
        settings.require_ci_fields()


def test_require_ci_fields_ok() -> None:
    settings = AppSettings(
        acr_name="acr",
        acr_resource_group="rg",
        repo_name="repo",
        tag="1.0.0",
        dockerfile_path=Path("Dockerfile"),
        build_context=Path("."),
    )
    settings.require_ci_fields()
