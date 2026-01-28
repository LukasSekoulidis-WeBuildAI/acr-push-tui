"Core workflow logic shared by TUI and CI mode."

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from acr_push_tui.services import azure, docker


class WorkflowError(RuntimeError):
    """Raised when workflow steps fail."""


@dataclass(frozen=True)
class BuildPlan:
    """Resolved build and push plan."""

    registry_server: str
    repository: str
    tag: str
    dockerfile_path: Path
    build_context: Path
    skip_latest: bool
    platform: str | None

    @property
    def versioned_ref(self) -> str:
        return f"{self.registry_server}/{self.repository}:{self.tag}"

    @property
    def latest_ref(self) -> str:
        return f"{self.registry_server}/{self.repository}:latest"


def resolve_registry(acr_name: str, resource_group: str) -> azure.AcrRegistry:
    """Resolve registry details."""
    try:
        return azure.show_registry(acr_name=acr_name, resource_group=resource_group)
    except azure.AzureCliError as exc:
        raise WorkflowError(str(exc)) from exc


def validate_docker_paths(dockerfile_path: Path, build_context: Path) -> None:
    """Validate dockerfile and build context paths."""
    if not dockerfile_path.is_file():
        raise WorkflowError(f"Dockerfile not found: {dockerfile_path}")
    if not build_context.is_dir():
        raise WorkflowError(f"Build context not found: {build_context}")


def build_and_push(
    plan: BuildPlan,
    on_output: Callable[[str], None] | None = None,
    on_command: Callable[[str], None] | None = None,
) -> None:
    """Execute build and push steps."""
    try:
        docker.ensure_available(on_output=on_output, on_command=on_command)
        docker.build_image(
            tag=plan.versioned_ref,
            dockerfile_path=plan.dockerfile_path,
            context_path=plan.build_context,
            platform=plan.platform,
            on_output=on_output,
            on_command=on_command,
        )
        if not plan.skip_latest:
            docker.tag_image(
                plan.versioned_ref,
                plan.latest_ref,
                on_output=on_output,
                on_command=on_command,
            )
        docker.push_image(plan.versioned_ref, on_output=on_output, on_command=on_command)
        if not plan.skip_latest:
            docker.push_image(plan.latest_ref, on_output=on_output, on_command=on_command)
    except (docker.DockerCliError, RuntimeError) as exc:
        raise WorkflowError(str(exc)) from exc
