"Docker CLI integration."

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Callable

from acr_push_tui.services.subprocess_runner import CommandError, run_command


class DockerCliError(RuntimeError):
    """Raised when Docker CLI calls fail."""


def ensure_available(
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Ensure Docker CLI and daemon are available.

    Raises:
        DockerCliError: If Docker is not available.
    """
    try:
        args = ["docker", "info"]
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise DockerCliError("Docker daemon is not running.") from exc


def build_image(
    tag: str,
    dockerfile_path: Path,
    context_path: Path,
    platform: str | None = None,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Build a Docker image.

    Args:
        tag: Image tag.
        dockerfile_path: Path to Dockerfile.
        context_path: Build context directory.
        platform: Optional platform string.

    Raises:
        DockerCliError: If build fails.
    """
    args = [
        "docker",
        "build",
        "-t",
        tag,
        "-f",
        str(dockerfile_path),
        str(context_path),
    ]
    if platform:
        args.insert(2, "--platform")
        args.insert(3, platform)
    try:
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise DockerCliError("Docker build failed.") from exc


def tag_image(
    source_tag: str,
    target_tag: str,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Tag an image.

    Args:
        source_tag: Existing tag.
        target_tag: New tag.

    Raises:
        DockerCliError: If tag fails.
    """
    try:
        args = ["docker", "tag", source_tag, target_tag]
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise DockerCliError("Docker tag failed.") from exc


def push_image(
    tag: str,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Push a tagged image.

    Args:
        tag: Tag to push.

    Raises:
        DockerCliError: If push fails.
    """
    try:
        args = ["docker", "push", tag]
        _emit_command(args, on_command)
        run_command(args, on_output=on_output)
    except CommandError as exc:
        raise DockerCliError(f"Failed to push image: {tag}") from exc


def _emit_command(args: list[str], on_command: Callable[[str], None] | None) -> None:
    if on_command:
        formatted = " ".join(shlex.quote(arg) for arg in args)
        on_command(formatted)
