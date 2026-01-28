"CLI entrypoint for acr-push-tui."

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from acr_push_tui.logging_config import configure_logging
from acr_push_tui.settings import AppSettings
from acr_push_tui.services import azure
from acr_push_tui.tui.app import AcrPushApp
from acr_push_tui.workflow import BuildPlan, WorkflowError, build_and_push, resolve_registry, validate_docker_paths

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, no_args_is_help=False, invoke_without_command=True)


def _merge_settings(settings: AppSettings, **overrides: object) -> AppSettings:
    data = settings.model_dump()
    for key, value in overrides.items():
        if value is None:
            continue
        data[key] = value
    return AppSettings(**data)


def _run_impl(
    ci: bool = typer.Option(False, "--ci", help="Run in non-interactive CI mode."),
    acr_name: Optional[str] = typer.Option(None, "--acr"),
    acr_resource_group: Optional[str] = typer.Option(None, "--rg"),
    subscription: Optional[str] = typer.Option(None, "--subscription"),
    tenant_id: Optional[str] = typer.Option(None, "--tenant-id"),
    repo_name: Optional[str] = typer.Option(None, "--repo"),
    tag: Optional[str] = typer.Option(None, "--tag"),
    dockerfile_path: Optional[Path] = typer.Option(None, "--dockerfile"),
    build_context: Optional[Path] = typer.Option(None, "--context"),
    skip_latest: bool = typer.Option(False, "--skip-latest"),
    platform: Optional[str] = typer.Option(None, "--platform"),
    log_level: Optional[str] = typer.Option(None, "--log-level"),
) -> None:
    """Run the application in TUI or CI mode."""
    settings = AppSettings()
    merged = _merge_settings(
        settings,
        acr_name=acr_name,
        acr_resource_group=acr_resource_group,
        subscription=subscription,
        tenant_id=tenant_id,
        repo_name=repo_name,
        tag=tag,
        dockerfile_path=dockerfile_path,
        build_context=build_context,
        skip_latest=skip_latest,
        platform=platform,
        log_level=log_level or settings.log_level,
    )
    configure_logging(merged.log_level)
    ci_flag = _normalize_bool(ci)
    if ci_flag:
        _run_ci(merged)
        return
    AcrPushApp(settings=merged).run()


@app.callback()
def cli(
    ctx: typer.Context,
    ci: bool = typer.Option(False, "--ci", help="Run in non-interactive CI mode."),
    acr_name: Optional[str] = typer.Option(None, "--acr"),
    acr_resource_group: Optional[str] = typer.Option(None, "--rg"),
    subscription: Optional[str] = typer.Option(None, "--subscription"),
    tenant_id: Optional[str] = typer.Option(None, "--tenant-id"),
    repo_name: Optional[str] = typer.Option(None, "--repo"),
    tag: Optional[str] = typer.Option(None, "--tag"),
    dockerfile_path: Optional[Path] = typer.Option(None, "--dockerfile"),
    build_context: Optional[Path] = typer.Option(None, "--context"),
    skip_latest: bool = typer.Option(False, "--skip-latest"),
    platform: Optional[str] = typer.Option(None, "--platform"),
    log_level: Optional[str] = typer.Option(None, "--log-level"),
) -> None:
    """CLI entrypoint."""
    if ctx.invoked_subcommand is None:
        _run_impl(
            ci=ci,
            acr_name=acr_name,
            acr_resource_group=acr_resource_group,
            subscription=subscription,
            tenant_id=tenant_id,
            repo_name=repo_name,
            tag=tag,
            dockerfile_path=dockerfile_path,
            build_context=build_context,
            skip_latest=skip_latest,
            platform=platform,
            log_level=log_level,
        )


@app.command()
def run(
    ci: bool = typer.Option(False, "--ci", help="Run in non-interactive CI mode."),
    acr_name: Optional[str] = typer.Option(None, "--acr"),
    acr_resource_group: Optional[str] = typer.Option(None, "--rg"),
    subscription: Optional[str] = typer.Option(None, "--subscription"),
    tenant_id: Optional[str] = typer.Option(None, "--tenant-id"),
    repo_name: Optional[str] = typer.Option(None, "--repo"),
    tag: Optional[str] = typer.Option(None, "--tag"),
    dockerfile_path: Optional[Path] = typer.Option(None, "--dockerfile"),
    build_context: Optional[Path] = typer.Option(None, "--context"),
    skip_latest: bool = typer.Option(False, "--skip-latest"),
    platform: Optional[str] = typer.Option(None, "--platform"),
    log_level: Optional[str] = typer.Option(None, "--log-level"),
) -> None:
    """Run the application in TUI or CI mode."""
    _run_impl(
        ci=ci,
        acr_name=acr_name,
        acr_resource_group=acr_resource_group,
        subscription=subscription,
        tenant_id=tenant_id,
        repo_name=repo_name,
        tag=tag,
        dockerfile_path=dockerfile_path,
        build_context=build_context,
        skip_latest=skip_latest,
        platform=platform,
        log_level=log_level,
    )


def _run_ci(settings: AppSettings) -> None:
    settings.require_ci_fields()
    azure.ensure_logged_in()
    azure.set_subscription(settings.subscription)
    registry = resolve_registry(
        acr_name=settings.acr_name or "",
        resource_group=settings.acr_resource_group or "",
    )
    azure.login_registry(registry.name)
    dockerfile_path = settings.dockerfile_path or Path()
    build_context = settings.build_context or Path()
    validate_docker_paths(dockerfile_path, build_context)
    plan = BuildPlan(
        registry_server=registry.login_server,
        repository=settings.repo_name or "",
        tag=settings.tag or "",
        dockerfile_path=dockerfile_path,
        build_context=build_context,
        skip_latest=settings.skip_latest,
        platform=settings.platform,
    )
    try:
        build_and_push(plan)
        logger.info("Build and push completed.")
    except WorkflowError as exc:
        logger.error("Build and push failed: %s", exc)
        raise typer.Exit(code=1) from exc


def _normalize_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def main() -> None:
    """Entry point for console script."""
    app()


if __name__ == "__main__":
    main()
