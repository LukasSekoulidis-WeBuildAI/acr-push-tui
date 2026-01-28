"Tests for workflow utilities."

from __future__ import annotations

from pathlib import Path

import pytest

from acr_push_tui.workflow import BuildPlan, WorkflowError, build_and_push, validate_docker_paths


def test_validate_docker_paths(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\n")
    validate_docker_paths(dockerfile, tmp_path)


def test_validate_docker_paths_missing(tmp_path: Path) -> None:
    with pytest.raises(WorkflowError):
        validate_docker_paths(tmp_path / "Dockerfile", tmp_path)


def test_build_and_push_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\n")
    plan = BuildPlan(
        registry_server="registry",
        repository="repo",
        tag="1.0.0",
        dockerfile_path=dockerfile,
        build_context=tmp_path,
        skip_latest=False,
        platform=None,
    )

    calls: list[str] = []

    def record(name: str) -> None:
        calls.append(name)

    monkeypatch.setattr("acr_push_tui.services.docker.ensure_available", lambda: record("ensure"))
    monkeypatch.setattr(
        "acr_push_tui.services.docker.build_image",
        lambda *args, **kwargs: record("build"),
    )
    monkeypatch.setattr(
        "acr_push_tui.services.docker.tag_image",
        lambda *args, **kwargs: record("tag"),
    )
    monkeypatch.setattr(
        "acr_push_tui.services.docker.push_image",
        lambda *args, **kwargs: record("push"),
    )

    build_and_push(plan)
    assert calls == ["ensure", "build", "tag", "push", "push"]
