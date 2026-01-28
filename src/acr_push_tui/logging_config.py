"Logging configuration helpers."

from __future__ import annotations

import logging
from typing import Final


DEFAULT_LOG_LEVEL: Final[str] = "INFO"


def configure_logging(level: str | None = None) -> None:
    """Configure application logging.

    Args:
        level: Optional log level override.

    Returns:
        None.

    Raises:
        ValueError: If level is invalid.
    """
    resolved = level or DEFAULT_LOG_LEVEL
    if not isinstance(resolved, str) or not resolved:
        raise ValueError("Log level must be a non-empty string.")
    logging.basicConfig(
        level=resolved.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
