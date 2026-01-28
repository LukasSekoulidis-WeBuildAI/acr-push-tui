"Application settings via pydantic-settings."

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """App settings loaded from environment and CLI overrides.

    Args:
        None.

    Returns:
        None.

    Raises:
        ValueError: If any validation fails.
    """

    model_config = SettingsConfigDict(
        env_prefix="ACR_PUSH_",
        env_file=".env",
        case_sensitive=False,
    )

    acr_name: str | None = None
    acr_resource_group: str | None = None
    subscription: str | None = None
    tenant_id: str | None = None
    repo_name: str | None = None
    tag: str | None = None
    dockerfile_path: Path | None = None
    build_context: Path | None = None
    skip_latest: bool = False
    platform: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    def require_ci_fields(self) -> None:
        """Validate required fields for CI mode.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If any required field is missing.
        """
        missing = [
            name
            for name in (
                "acr_name",
                "acr_resource_group",
                "repo_name",
                "tag",
                "dockerfile_path",
                "build_context",
            )
            if getattr(self, name) in (None, "", Path())
        ]
        if missing:
            raise ValueError(f"Missing required settings for CI: {', '.join(missing)}")
